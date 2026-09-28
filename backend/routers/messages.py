import base64
import binascii
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import ConversationMember, Message, MessageAttachment, MessageStatus, User
from ..schemas import EncryptedAttachmentOut, EncryptedMessageCreate, MessageOut
from ..websocket import manager
from .conversations import conversation_for_user


router = APIRouter(tags=["messages"])
MAX_ENCRYPTED_IMAGE_BYTES = 5 * 1024 * 1024 + 4096
IMAGE_DISPLAY_SECONDS = 10
TEXT_DISPLAY_SECONDS = 10


def aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def decode_encryption_metadata(nonce: str, sender_key: str, recipient_key: str) -> tuple[bytes, bytes, bytes]:
    try:
        decoded = (
            base64.b64decode(nonce, validate=True),
            base64.b64decode(sender_key, validate=True),
            base64.b64decode(recipient_key, validate=True),
        )
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid encryption metadata") from exc
    if len(decoded[0]) != 12 or not (128 <= len(decoded[1]) <= 1024) or not (128 <= len(decoded[2]) <= 1024):
        raise HTTPException(status_code=422, detail="Invalid encryption metadata")
    return decoded


def serialize_message(message: Message, viewer_id: int, reveal: bool = False) -> MessageOut:
    now = datetime.now(timezone.utc)
    expires_at = aware(message.expires_at)
    currently_visible = message.status == MessageStatus.opened and expires_at and expires_at > now
    can_see = message.sender_id == viewer_id or reveal or (message.recipient_id == viewer_id and currently_visible)
    can_reveal = can_see and message.status != MessageStatus.expired
    is_image = message.attachment is not None
    encrypted_key = message.sender_key if message.sender_id == viewer_id else message.recipient_key
    seconds = (IMAGE_DISPLAY_SECONDS if is_image else TEXT_DISPLAY_SECONDS) if message.opened_at else None
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        recipient_id=message.recipient_id,
        content=None,
        ciphertext=base64.b64encode(message.encrypted_content).decode("ascii") if message.encrypted_content and can_reveal else None,
        nonce=message.nonce if message.encrypted_content and can_reveal else None,
        encrypted_key=encrypted_key if message.encrypted_content and can_reveal else None,
        created_at=aware(message.created_at),
        delivered_at=aware(message.delivered_at),
        opened_at=aware(message.opened_at),
        expires_at=expires_at,
        status=message.status.value,
        display_seconds=seconds,
        kind="image" if is_image else "text",
        attachment_name=None,
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
        item.encrypted_content = None
        item.nonce = None
        item.sender_key = None
        item.recipient_key = None
        if item.attachment:
            item.attachment.data = None
            item.attachment.nonce = None
            item.attachment.sender_key = None
            item.attachment.recipient_key = None
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
    payload: EncryptedMessageCreate,
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

    if not current_user.public_key:
        raise HTTPException(status_code=409, detail="Set up message encryption before sending messages")
    recipient = db.get(User, recipient_id)
    if not recipient or not recipient.public_key:
        raise HTTPException(status_code=409, detail="Recipient has not set up message encryption")
    try:
        ciphertext = base64.b64decode(payload.ciphertext, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invalid encrypted message") from exc
    if not (16 < len(ciphertext) <= 4096):
        raise HTTPException(status_code=422, detail="Invalid encrypted message")
    decode_encryption_metadata(payload.nonce, payload.sender_key, payload.recipient_key)

    now = datetime.now(timezone.utc)
    is_delivered = manager.is_online(recipient_id)
    message = Message(
        conversation_id=payload.conversation_id,
        sender_id=current_user.id,
        recipient_id=recipient_id,
        encrypted_content=ciphertext,
        nonce=payload.nonce,
        sender_key=payload.sender_key,
        recipient_key=payload.recipient_key,
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
    nonce: str = Form(),
    sender_key: str = Form(),
    recipient_key: str = Form(),
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

    if not current_user.public_key:
        raise HTTPException(status_code=409, detail="Set up image encryption before sending images")
    recipient = db.get(User, recipient_id)
    if not recipient or not recipient.public_key:
        raise HTTPException(status_code=409, detail="Recipient has not set up image encryption")

    data = await file.read(MAX_ENCRYPTED_IMAGE_BYTES + 1)
    await file.close()
    if len(data) <= 16:
        raise HTTPException(status_code=422, detail="Encrypted image cannot be empty")
    if len(data) > MAX_ENCRYPTED_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Encrypted image is too large")
    decode_encryption_metadata(nonce, sender_key, recipient_key)

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
        mime_type="application/octet-stream",
        filename="encrypted-image",
        nonce=nonce,
        sender_key=sender_key,
        recipient_key=recipient_key,
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


@router.get("/messages/{message_id}/attachment", response_model=EncryptedAttachmentOut)
async def get_attachment(
    message_id: int,
    response: Response,
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
    encrypted_key = message.attachment.sender_key if current_user.id == message.sender_id else message.attachment.recipient_key
    if not message.attachment.nonce or not encrypted_key:
        raise HTTPException(status_code=410, detail="Image encryption data is unavailable")
    response.headers["Cache-Control"] = "no-store"
    return EncryptedAttachmentOut(
        ciphertext=base64.b64encode(message.attachment.data).decode("ascii"),
        nonce=message.attachment.nonce,
        encrypted_key=encrypted_key,
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
    has_text = message.encrypted_content is not None
    if message.status == MessageStatus.expired or (not has_text and not has_image):
        raise HTTPException(status_code=410, detail="Message has expired")

    seconds = IMAGE_DISPLAY_SECONDS if has_image else TEXT_DISPLAY_SECONDS
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
