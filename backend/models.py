import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MessageStatus(str, enum.Enum):
    sent = "sent"
    delivered = "delivered"
    opened = "opened"
    expired = "expired"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(32), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    members = relationship("ConversationMember", cascade="all, delete-orphan")


class ConversationMember(Base):
    __tablename__ = "conversation_members"
    __table_args__ = (UniqueConstraint("conversation_id", "user_id"),)

    conversation_id = Column(ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    user = relationship("User")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(ForeignKey("users.id"), nullable=False, index=True)
    recipient_id = Column(ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    status = Column(Enum(MessageStatus), default=MessageStatus.sent, nullable=False, index=True)
    attachment = relationship("MessageAttachment", back_populates="message", cascade="all, delete-orphan", uselist=False)


class MessageAttachment(Base):
    __tablename__ = "message_attachments"

    message_id = Column(ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    data = Column(LargeBinary, nullable=True)
    mime_type = Column(String(32), nullable=False)
    filename = Column(String(255), nullable=False)
    message = relationship("Message", back_populates="attachment")
