import asyncio
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket) -> bool:
        await websocket.accept()
        async with self._lock:
            first_connection = not self._connections[user_id]
            self._connections[user_id].add(websocket)
        return first_connection

    async def disconnect(self, user_id: int, websocket: WebSocket) -> bool:
        async with self._lock:
            self._connections[user_id].discard(websocket)
            if self._connections[user_id]:
                return False
            self._connections.pop(user_id, None)
            return True

    def is_online(self, user_id: int) -> bool:
        return bool(self._connections.get(user_id))

    async def send_user(self, user_id: int, event: dict) -> None:
        sockets = list(self._connections.get(user_id, set()))
        dead: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_json(event)
            except Exception:
                dead.append(socket)
        if dead:
            async with self._lock:
                for socket in dead:
                    self._connections[user_id].discard(socket)
                if not self._connections[user_id]:
                    self._connections.pop(user_id, None)

    async def send_users(self, user_ids: set[int], event: dict) -> None:
        await asyncio.gather(*(self.send_user(user_id, event) for user_id in user_ids))

    async def broadcast(self, event: dict, exclude: int | None = None) -> None:
        user_ids = set(self._connections)
        if exclude is not None:
            user_ids.discard(exclude)
        await self.send_users(user_ids, event)


manager = ConnectionManager()
