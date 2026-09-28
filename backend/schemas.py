import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def validate_encryption_public_key(value: str) -> str:
    try:
        key = json.loads(value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("public_key must be a JSON Web Key") from exc
    private_fields = {"d", "p", "q", "dp", "dq", "qi", "oth"}
    if (
        not isinstance(key, dict)
        or key.get("kty") != "RSA"
        or key.get("e") != "AQAB"
        or not isinstance(key.get("n"), str)
        or len(key["n"]) < 300
        or private_fields.intersection(key)
        or "encrypt" not in key.get("key_ops", [])
    ):
        raise ValueError("public_key must be a public RSA-OAEP encryption key")
    return value


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=6, max_length=128)
    public_key: str = Field(min_length=100, max_length=4096)

    _validate_public_key = field_validator("public_key")(validate_encryption_public_key)


class UserLogin(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=6, max_length=128)


class EncryptionKeyUpdate(BaseModel):
    public_key: str = Field(min_length=100, max_length=4096)

    _validate_public_key = field_validator("public_key")(validate_encryption_public_key)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime
    public_key: str | None = None


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


class EncryptedMessageCreate(BaseModel):
    conversation_id: int
    ciphertext: str = Field(min_length=24, max_length=8192)
    nonce: str = Field(min_length=16, max_length=64)
    sender_key: str = Field(min_length=128, max_length=2048)
    recipient_key: str = Field(min_length=128, max_length=2048)


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    recipient_id: int
    content: str | None
    ciphertext: str | None = None
    nonce: str | None = None
    encrypted_key: str | None = None
    created_at: datetime
    delivered_at: datetime | None
    opened_at: datetime | None
    expires_at: datetime | None
    status: str
    display_seconds: int | None = None
    kind: str = "text"
    attachment_name: str | None = None


class EncryptedAttachmentOut(BaseModel):
    ciphertext: str
    nonce: str
    encrypted_key: str
