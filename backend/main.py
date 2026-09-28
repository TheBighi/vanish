import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, select, text

from .auth import SECRET_KEY, decode_token
from .database import Base, SessionLocal, engine
from .models import ConversationMember, Message, MessageStatus, User
from .routers import auth, conversations, messages, users
from .websocket import manager


async def cleanup_expired_messages() -> None:
    while True:
        await asyncio.sleep(1)
        with SessionLocal() as db:
            events = messages.expire_due_messages(db)
        await messages.notify_expired(events)


def migrate_encryption_columns() -> None:
    columns = inspect(engine).get_columns("users")
    message_columns = inspect(engine).get_columns("messages")
    attachment_columns = inspect(engine).get_columns("message_attachments")
    with engine.begin() as connection:
        if "public_key" not in {column["name"] for column in columns}:
            connection.execute(text("ALTER TABLE users ADD COLUMN public_key TEXT"))
        existing_messages = {column["name"] for column in message_columns}
        for name, column_type in (("encrypted_content", "BLOB"), ("nonce", "VARCHAR(64)"), ("sender_key", "TEXT"), ("recipient_key", "TEXT")):
            if name not in existing_messages:
                connection.execute(text(f"ALTER TABLE messages ADD COLUMN {name} {column_type}"))
        existing = {column["name"] for column in attachment_columns}
        for name, column_type in (("nonce", "VARCHAR(64)"), ("sender_key", "TEXT"), ("recipient_key", "TEXT")):
            if name not in existing:
                connection.execute(text(f"ALTER TABLE message_attachments ADD COLUMN {name} {column_type}"))
        # Legacy attachments contain plaintext and cannot safely remain after enabling E2E images.
        connection.execute(text("UPDATE message_attachments SET data = NULL WHERE data IS NOT NULL AND nonce IS NULL"))
        connection.execute(text("""
            UPDATE messages SET content = NULL, status = 'expired'
            WHERE id IN (SELECT message_id FROM message_attachments WHERE nonce IS NULL)
        """))
        connection.execute(text("""
            UPDATE messages SET content = NULL, status = 'expired'
            WHERE content IS NOT NULL AND encrypted_content IS NULL
        """))


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY environment variable is required")
    Base.metadata.create_all(bind=engine)
    migrate_encryption_columns()
    cleanup_task = asyncio.create_task(cleanup_expired_messages())
    yield
    cleanup_task.cancel()
    with suppress(asyncio.CancelledError):
        await cleanup_task


app = FastAPI(title="Vanish Chat API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(conversations.router)
app.include_router(messages.router)


@app.get("/health")
def health():
    return {"status": "ok"}


def conversation_member_ids(db, conversation_id: int) -> set[int]:
    return set(
        db.scalars(
            select(ConversationMember.user_id).where(ConversationMember.conversation_id == conversation_id)
        ).all()
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str):
    try:
        user_id = decode_token(token)
    except Exception:
        await websocket.close(code=4401)
        return
    with SessionLocal() as db:
        if not db.get(User, user_id):
            await websocket.close(code=4401)
            return

    await manager.connect(user_id, websocket)

    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        undelivered = db.scalars(
            select(Message).where(Message.recipient_id == user_id, Message.status == MessageStatus.sent)
        ).all()
        delivered_events: list[dict] = []
        for message in undelivered:
            message.status = MessageStatus.delivered
            message.delivered_at = now
            delivered_events.append(
                {"type": "message:delivered", "data": {"message": messages.serialize_message(message, message.sender_id).model_dump(mode="json")}}
            )
        if undelivered:
            db.commit()
        for item, event in zip(undelivered, delivered_events):
            await manager.send_user(
                user_id,
                {"type": "message:new", "data": {"message": messages.serialize_message(item, user_id).model_dump(mode="json")}},
            )
            sender_id = item.sender_id
            await manager.send_user(sender_id, event)

    try:
        while True:
            event = await websocket.receive_json()
            event_type = event.get("type")
            data = event.get("data") or {}
            if event_type not in {"typing:start", "typing:stop"}:
                continue
            try:
                conversation_id = int(data.get("conversation_id"))
            except (TypeError, ValueError):
                continue
            with SessionLocal() as db:
                member_ids = conversation_member_ids(db, conversation_id)
            if user_id not in member_ids:
                continue
            await manager.send_users(
                member_ids - {user_id},
                {"type": event_type, "data": {"conversation_id": conversation_id, "user_id": user_id}},
            )
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await manager.disconnect(user_id, websocket)
