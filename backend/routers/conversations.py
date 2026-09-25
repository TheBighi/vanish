from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Conversation, ConversationMember, Message, MessageStatus, User
from ..schemas import ConversationCreate, ConversationOut


router = APIRouter(prefix="/conversations", tags=["conversations"])


def conversation_for_user(db: Session, conversation_id: int, user_id: int) -> Conversation:
    conversation = db.scalar(
        select(Conversation)
        .join(ConversationMember)
        .where(Conversation.id == conversation_id, ConversationMember.user_id == user_id)
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def serialize_conversation(db: Session, conversation: Conversation, user_id: int) -> ConversationOut:
    other = db.scalar(
        select(User)
        .join(ConversationMember, ConversationMember.user_id == User.id)
        .where(ConversationMember.conversation_id == conversation.id, User.id != user_id)
    )
    unread = db.scalar(
        select(func.count(Message.id)).where(
            Message.conversation_id == conversation.id,
            Message.recipient_id == user_id,
            Message.opened_at.is_(None),
            Message.status.in_([MessageStatus.sent, MessageStatus.delivered]),
        )
    )
    return ConversationOut(
        id=conversation.id,
        created_at=conversation.created_at,
        other_user=other,
        unread_count=unread or 0,
    )


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversations = db.scalars(
        select(Conversation)
        .join(ConversationMember)
        .where(ConversationMember.user_id == current_user.id)
        .order_by(Conversation.created_at.desc())
    ).all()
    return [serialize_conversation(db, item, current_user.id) for item in conversations]


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    other = db.scalar(select(User).where(func.lower(User.username) == payload.username.strip().lower()))
    if not other:
        raise HTTPException(status_code=404, detail="User not found")
    if other.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot message yourself")

    existing = db.scalar(
        select(Conversation)
        .join(ConversationMember)
        .where(ConversationMember.user_id == current_user.id)
        .where(
            Conversation.id.in_(
                select(ConversationMember.conversation_id).where(ConversationMember.user_id == other.id)
            )
        )
    )
    if existing:
        return serialize_conversation(db, existing, current_user.id)

    conversation = Conversation()
    db.add(conversation)
    db.flush()
    db.add_all(
        [
            ConversationMember(conversation_id=conversation.id, user_id=current_user.id),
            ConversationMember(conversation_id=conversation.id, user_id=other.id),
        ]
    )
    db.commit()
    db.refresh(conversation)
    return serialize_conversation(db, conversation, current_user.id)
