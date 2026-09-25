# Vanish Chat

Vanish Chat is a small private-chat application where received messages stay sealed until the recipient explicitly opens them. An opened message is shown for a server-calculated period, then its plaintext is removed from SQLite and both participants are notified in real time.

## Stack

- React and Vite frontend
- FastAPI REST API and WebSocket endpoint
- SQLite with SQLAlchemy
- JWT bearer authentication
- Plain CSS responsive dark interface

This project is **not end-to-end encrypted**. The server receives and temporarily stores plaintext so it can deliver the message. The message APIs and UI isolate content handling so client-side encryption can be added later, but the current version must not be treated as E2E secure.

## Project Structure

```text
backend/
  main.py             application, WebSocket endpoint, cleanup task
  database.py         SQLite engine and sessions
  models.py           SQLAlchemy models
  schemas.py          API request/response models
  auth.py             password hashing and JWT helpers
  websocket.py        in-memory connection manager
  routers/            auth, users, conversations, messages
frontend/
  src/
    components/       chat UI components
    hooks/            reconnecting WebSocket hook
    pages/            authentication and chat screens
    services/         REST client and local session helpers
requirements.txt
```

## Setup

Python 3.11 or newer and Node.js 20 or newer are recommended.

From the project root, create and start the backend:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="replace-this-with-a-long-random-value"
uvicorn backend.main:app --reload
```

The API runs at `http://localhost:8000`. SQLite tables and `disappearing_chat.db` are created automatically on startup. Interactive API documentation is available at `http://localhost:8000/docs`.

In a second terminal, start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Register two accounts and use two browsers or one private window to test real-time delivery.

Optional frontend environment variables:

```bash
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

## Expiration Lifecycle

1. `POST /messages` stores a message in `sent` state. If the recipient has an active WebSocket, it is immediately marked `delivered`.
2. Message list responses omit content for an unopened incoming message. The WebSocket `message:new` event also omits that content.
3. Only the matching `recipient_id` may call `POST /messages/{id}/open`.
4. A conditional SQL update requiring `opened_at IS NULL` atomically sets `opened_at`, `expires_at`, and `status = opened`. A second open attempt fails with HTTP 409.
5. Display time is calculated on the server:

```python
max(2, min(30, math.ceil(len(message) / 15)))
```

6. The frontend uses the server's `expires_at` for its countdown and progress bar. It removes plaintext from React state when that time is reached.
7. A FastAPI background task checks every second for due messages. It sets `content = NULL`, changes the status to `expired`, commits the deletion, and emits `message:expired` to both users.
8. API reads also enforce the expiry state. Refreshing, altering the client timer, or calling open again cannot reveal expired content.

Image messages accept JPEG, PNG, GIF, or WebP files up to 5 MB. Their bytes are stored in the `message_attachments` SQLite table while sealed. After the recipient opens an image, it is available through an authenticated, non-cacheable endpoint for 10 seconds. Expiration sets the stored binary data to `NULL` and revokes the browser object URL.

The WebSocket connection manager is intentionally in memory. This is suitable for a single-process school project. Run one Uvicorn worker; multiple workers would require shared presence/pub-sub infrastructure such as Redis.

## API Examples

Register and save the returned token:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"secret123"}'
```

Log in:

```bash
curl -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"secret123"}'
```

Start a conversation by submitting the exact username, then send a message:

```bash
curl -X POST http://localhost:8000/conversations \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"username":"bob"}'

curl -X POST http://localhost:8000/messages \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":1,"content":"Are we meeting tomorrow?"}'
```

Send an image:

```bash
curl -X POST http://localhost:8000/messages/image \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -F 'conversation_id=1' \
  -F 'file=@photo.jpg'
```

Open a message as its recipient:

```bash
curl -X POST http://localhost:8000/messages/1/open \
  -H 'Authorization: Bearer RECIPIENT_TOKEN'
```

Connect a WebSocket with `ws://localhost:8000/ws?token=YOUR_TOKEN`. Client events use this shape:

```json
{"type":"typing:start","data":{"conversation_id":1}}
```

Server event types are `message:new`, `message:delivered`, `message:opened`, `message:expired`, `typing:start`, and `typing:stop`.

## Adding E2E Encryption for Images

The current image implementation is not end-to-end encrypted because the backend receives the original image bytes. To add E2E encryption, each account would need a client-generated public/private key pair. Before upload, the sender's browser would generate a random symmetric key, encrypt the image locally with an authenticated cipher such as AES-256-GCM, and encrypt that symmetric key to the recipient's public key. The backend would store only ciphertext, an IV/nonce, and the encrypted image key. The recipient would download the ciphertext and decrypt it in the browser with their private key.

Private keys must never be sent to the backend. They need secure local storage and a recovery or multi-device key-transfer design. Public-key verification is also required to prevent the server from replacing a recipient's public key. Until those pieces are implemented and audited, this application should not be described as E2E encrypted.

## Security Notes

- Set a strong `SECRET_KEY` outside development.
- Passwords are bcrypt hashes, never plaintext.
- Conversation membership is checked for message history, sending, opening, and typing events.
- A valid JWT is required for REST resources and WebSockets.
- Production deployment should use HTTPS/WSS and a restricted CORS origin.
- Expired rows remain for status/history, but their `content` field is permanently set to `NULL`.
