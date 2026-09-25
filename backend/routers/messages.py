import math
from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import ConversationMember, Message, MessageAttachment, MessageStatus, User
from ..schemas import MessageCreate, MessageOut
from ..websocket import manager
from .conversations import conversation_for_user


router = APIRouter(tags=["messages"])
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_DISPLAY_SECONDS = 10
IMAGE_MIME_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "GIF": "image/gif",
    "WEBP": "image/webp",
}


def aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def display_seconds(content: str) -> int:
    return max(2, min(30, math.ceil(len(content) / 15)))


def serialize_message(message: Message, viewer_id: int, reveal: bool = False) -> MessageOut:
    now = datetime.now(timezone.utc)
    expires_at = aware(message.expires_at)
    currently_visible = message.status == MessageStatus.opened and expires_at and expires_at > now
    can_see = message.sender_id == viewer_id or reveal or (message.recipient_id == viewer_id and currently_visible)
    content = message.content if can_see and message.status != MessageStatus.expired else None
    is_image = message.attachment is not None
    seconds = (IMAGE_DISPLAY_SECONDS if is_image else display_seconds(message.content)) if message.opened_at else None
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        recipient_id=message.recipient_id,
        content=content,
        created_at=aware(message.created_at),
        delivered_at=aware(message.delivered_at),
        opened_at=aware(message.opened_at),
        expires_at=expires_at,
        status=message.status.value,
        display_seconds=seconds,
        kind="image" if is_image else "text",
        attachment_name=message.attachment.filename if is_image and can_see and message.status != MessageStatus.expired else None,
    )


def expire_due_messages(db: Session) -> list[tuple[int, int, int]]:
    now = datetime.now(timezone.utc)
    due = db.scalars(
        select(Message).where(
            Message.status == MessageStatus.opened,
            Message.expires_at.is_not(None),
            Message.expires_at <= now,
        )
    ).all()
    events = [(item.id, item.sender_id, item.recipient_id) for item in due]
    for item in due:
        item.content = None
        if item.attachment:
            item.attachment.data = None
        item.status = MessageStatus.expired
    if due:
        db.commit()
    return events


async def notify_expired(events: list[tuple[int, int, int]]) -> None:
    for message_id, sender_id, recipient_id in events:
        event = {"type": "message:expired", "data": {"message_id": message_id}}
        await manager.send_users({sender_id, recipient_id}, event)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation_for_user(db, conversation_id, current_user.id)
    await notify_expired(expire_due_messages(db))
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    ).all()
    return [serialize_message(item, current_user.id) for item in messages]


@router.post("/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def send_message(
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation_for_user(db, payload.conversation_id, current_user.id)
    recipient_id = db.scalar(
        select(ConversationMember.user_id).where(
            ConversationMember.conversation_id == payload.conversation_id,
            ConversationMember.user_id != current_user.id,
        )
    )
    if not recipient_id:
        raise HTTPException(status_code=400, detail="Conversation has no recipient")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message cannot be blank")
    now = datetime.now(timezone.utc)
    is_delivered = manager.is_online(recipient_id)
    message = Message(
        conversation_id=payload.conversation_id,
        sender_id=current_user.id,
        recipient_id=recipient_id,
        content=content,
        delivered_at=now if is_delivered else None,
        status=MessageStatus.delivered if is_delivered else MessageStatus.sent,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    sender_view = serialize_message(message, current_user.id)
    recipient_view = serialize_message(message, recipient_id)
    await manager.send_user(recipient_id, {"type": "message:new", "data": {"message": recipient_view.model_dump(mode="json")}})
    if is_delivered:
        await manager.send_user(current_user.id, {"type": "message:delivered", "data": {"message": sender_view.model_dump(mode="json")}})
    return sender_view


@router.post("/messages/image", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def send_image(
    conversation_id: int = Form(),
    file: UploadFile = File(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation_for_user(db, conversation_id, current_user.id)
    recipient_id = db.scalar(
        select(ConversationMember.user_id).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id != current_user.id,
        )
    )
    if not recipient_id:
        raise HTTPException(status_code=400, detail="Conversation has no recipient")

    data = await file.read(MAX_IMAGE_BYTES + 1)
    await file.close()
    if not data:
        raise HTTPException(status_code=422, detail="Image cannot be empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 5 MB or smaller")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
            mime_type = IMAGE_MIME_TYPES.get(image.format)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=422, detail="File is not a valid image") from exc
    if not mime_type:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG, GIF, and WebP images are supported")

    now = datetime.now(timezone.utc)
    is_delivered = manager.is_online(recipient_id)
    message = Message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        recipient_id=recipient_id,
        delivered_at=now if is_delivered else None,
        status=MessageStatus.delivered if is_delivered else MessageStatus.sent,
    )
    message.attachment = MessageAttachment(
        data=data,
        mime_type=mime_type,
        filename=Path(file.filename or "image").name[:255],
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    sender_view = serialize_message(message, current_user.id)
    recipient_view = serialize_message(message, recipient_id)
    await manager.send_user(recipient_id, {"type": "message:new", "data": {"message": recipient_view.model_dump(mode="json")}})
    if is_delivered:
        await manager.send_user(current_user.id, {"type": "message:delivered", "data": {"message": sender_view.model_dump(mode="json")}})
    return sender_view


@router.get("/messages/{message_id}/attachment")
async def get_attachment(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    await notify_expired(expire_due_messages(db))
    message = db.get(Message, message_id)
    if not message or not message.attachment:
        raise HTTPException(status_code=404, detail="Image not found")
    if current_user.id not in {message.sender_id, message.recipient_id}:
        raise HTTPException(status_code=403, detail="You cannot access this image")
    if message.status == MessageStatus.expired or not message.attachment.data:
        raise HTTPException(status_code=410, detail="Image has expired")
    if message.recipient_id == current_user.id and message.status != MessageStatus.opened:
        raise HTTPException(status_code=403, detail="Image has not been opened")
    return Response(
        content=message.attachment.data,
        media_type=message.attachment.mime_type,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/messages/{message_id}/open", response_model=MessageOut)
async def open_message(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    await notify_expired(expire_due_messages(db))
    message = db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.recipient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the intended recipient can open this message")
    has_image = message.attachment is not None and message.attachment.data is not None
    if message.status == MessageStatus.expired or (not message.content and not has_image):
        raise HTTPException(status_code=410, detail="Message has expired")

    seconds = IMAGE_DISPLAY_SECONDS if has_image else display_seconds(message.content)
    result = db.execute(
        update(Message)
        .where(
            Message.id == message_id,
            Message.recipient_id == current_user.id,
            Message.opened_at.is_(None),
            Message.status.in_([MessageStatus.sent, MessageStatus.delivered]),
        )
        .values(opened_at=now, expires_at=now + timedelta(seconds=seconds), status=MessageStatus.opened)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Message has already been opened")
    db.commit()
    message = db.get(Message, message_id)
    response = serialize_message(message, current_user.id, reveal=True)
    await manager.send_user(
        message.sender_id,
        {"type": "message:opened", "data": {"message": serialize_message(message, message.sender_id).model_dump(mode="json")}},
    )
    return response
