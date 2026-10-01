# Vanish Chat

A private-chat app where messages self-destruct after being opened. Content is end-to-end encrypted in the browser.

## Stack

- **Frontend:** React + Vite, plain CSS (dark mode responsive)
- **Backend:** FastAPI, WebSockets, SQLite + SQLAlchemy
- **Auth:** JWT bearer tokens
- **Encryption:** Browser-based AES-256-GCM + RSA-OAEP, private keys in IndexedDB

## Project Structure

```
backend/
  main.py         app, WebSocket endpoint, cleanup task
  database.py     SQLite engine and sessions
  models.py       SQLAlchemy models
  schemas.py      API request/response models
  auth.py         password hashing and JWT helpers
  websocket.py    in-memory connection manager
  routers/        auth, users, conversations, messages
frontend/
  src/
    components/   chat UI
    hooks/        WebSocket reconnect helper
    pages/        auth and chat screens
    services/     REST client and session helpers
requirements.txt
```

## Setup

**Backend**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="your-long-random-secret"
uvicorn backend.main:app --reload
```

API: `http://localhost:8000` (docs: `http://localhost:8000/docs`)

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Register two accounts and use two browsers to test real-time delivery.

## How It Works

1. **Send** – Messages are encrypted in the browser and stored in SQLite as ciphertext.
2. **Receive** – Unopened messages hide ciphertext; the WebSocket `message:new` event also omits it.
3. **Open** – Only the recipient can call `POST /messages/{id}/open`. After opening, plaintext is shown for 10 seconds then removed.
4. **Expire** – A background task deletes ciphertext after the display period. Expired messages remain in the DB with empty ciphertext.

## API Highlights

- `POST /auth/register` – requires browser-generated RSA-OAEP public JWK
- `POST /auth/login`
- `POST /conversations` – start a conversation with a username
- `POST /messages` – send text (ciphertext, nonce, wrapped keys)
- `POST /messages/image` – send images (JPEG/PNG/GIF/WebP, ≤5 MB)
- `POST /messages/{id}/open` – open a message (HTTP 409 on double-open)
- WebSocket: `ws://localhost:8000/ws?token=YOUR_TOKEN`

Events: `message:new`, `message:delivered`, `message:opened`, `message:expired`, `typing:start`, `typing:stop`.

## Security Notes

- Set a strong `SECRET_KEY` outside development.
- Passwords are bcrypt hashes; private keys never leave the browser.
- Production: use HTTPS/WSS and restrict CORS origin.
- This is a school project — no audited security, no multi-device recovery, no key transparency.

## Optional Env vars (frontend)

```
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```