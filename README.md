# Vanish Chat

Vanish Chat is a small private-chat application where received messages stay sealed until the recipient explicitly opens them. An opened message is shown briefly, then its ciphertext is removed from SQLite and both participants are notified in real time.

## Stack

- React and Vite frontend
- FastAPI REST API and WebSocket endpoint
- SQLite with SQLAlchemy
- JWT bearer authentication
- Plain CSS responsive dark interface

Text and image contents are end-to-end encrypted in the browser. Image MIME types and filenames are encrypted as well. The backend receives only ciphertext, nonces, public keys, and separately wrapped content keys.

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
2. Message list responses omit ciphertext and wrapped keys for an unopened incoming message. The WebSocket `message:new` event also omits them.
3. Only the matching `recipient_id` may call `POST /messages/{id}/open`.
4. A conditional SQL update requiring `opened_at IS NULL` atomically sets `opened_at`, `expires_at`, and `status = opened`. A second open attempt fails with HTTP 409.
5. Text and image messages use a fixed 10-second display period so plaintext length is not needed for server-side timing.
6. The frontend uses the server's `expires_at` for its countdown and progress bar. It removes decrypted content from React state when that time is reached.
7. A FastAPI background task checks every second for due messages. It deletes ciphertext and wrapped keys, changes the status to `expired`, commits the deletion, and emits `message:expired` to both users.
8. API reads also enforce the expiry state. Refreshing, altering the client timer, or calling open again cannot reveal expired content.

Image messages accept JPEG, PNG, GIF, or WebP files up to 5 MB. The sender's browser encrypts the file and its metadata with a fresh AES-256-GCM key, then wraps that key separately for the sender and recipient with their RSA-OAEP public keys. The server stores only ciphertext, a nonce, and wrapped keys. After the recipient opens an image, the encrypted payload is available through an authenticated, non-cacheable endpoint for 10 seconds and is decrypted only in the browser. Expiration sets the ciphertext to `NULL` and revokes the browser object URL.

Private keys are non-extractable Web Crypto keys stored in IndexedDB and never sent to the backend. They remain on the browser where the account was created or where encryption was first provisioned. Losing that browser's storage means losing access to messages encrypted for that key; there is intentionally no server-side key recovery.

The WebSocket connection manager is intentionally in memory. This is suitable for a single-process school project. Run one Uvicorn worker; multiple workers would require shared presence/pub-sub infrastructure such as Redis.

## API Examples

Register through the web UI so the browser can generate and retain the private key. Direct API registration also requires a browser-generated RSA-OAEP public JWK in the `public_key` field:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"secret123","public_key":"PUBLIC_JWK_JSON"}'
```

Log in:

```bash
curl -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"secret123"}'
```

Start a conversation by submitting the exact username. Sending a text message requires browser-generated ciphertext and encryption metadata:

```bash
curl -X POST http://localhost:8000/conversations \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"username":"bob"}'

curl -X POST http://localhost:8000/messages \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":1,"ciphertext":"BASE64_AES_GCM_CIPHERTEXT","nonce":"BASE64_AES_GCM_NONCE","sender_key":"BASE64_WRAPPED_KEY","recipient_key":"BASE64_WRAPPED_KEY"}'
```

The browser sends an encrypted image using this multipart shape:

```bash
curl -X POST http://localhost:8000/messages/image \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -F 'conversation_id=1' \
  -F 'file=@ciphertext.bin' \
  -F 'nonce=BASE64_AES_GCM_NONCE' \
  -F 'sender_key=BASE64_WRAPPED_KEY' \
  -F 'recipient_key=BASE64_WRAPPED_KEY'
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

## Encryption Limits

End-to-end encryption protects stored and transported message contents from the application backend. The app does not yet provide multi-device key transfer, recovery, safety-number verification, or key transparency. A compromised server could substitute a public key before a conversation starts, so users should not treat this school project as an audited secure messenger.

## Security Notes

- Set a strong `SECRET_KEY` outside development.
- Passwords are bcrypt hashes, never plaintext.
- Conversation membership is checked for message history, sending, opening, and typing events.
- A valid JWT is required for REST resources and WebSockets.
- Private keys are generated and used through Web Crypto and remain non-extractable in IndexedDB.
- Production deployment should use HTTPS/WSS and a restricted CORS origin.
- Expired rows remain for status/history, but their ciphertext and wrapped keys are permanently set to `NULL`.
