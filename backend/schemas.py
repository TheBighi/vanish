from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=6, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ConversationCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")


class ConversationOut(BaseModel):
    id: int
    created_at: datetime
    other_user: UserOut
    unread_count: int


class MessageCreate(BaseModel):
    conversation_id: int
    content: str = Field(min_length=1, max_length=450)


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    recipient_id: int
    content: str | None
    created_at: datetime
    delivered_at: datetime | None
    opened_at: datetime | None
    expires_at: datetime | None
    status: str
    display_seconds: int | None = None
    kind: str = "text"
    attachment_name: str | None = None
