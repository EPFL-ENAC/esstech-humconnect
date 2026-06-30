import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import WebSocket


class ChatRoomConnectionHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._subscribers: set[asyncio.Queue[dict | None]] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict | None]]:
        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    async def broadcast(self, event: dict) -> None:
        async with self._lock:
            sockets = list(self._connections)
            subscribers = list(self._subscribers)

        for queue in subscribers:
            queue.put_nowait(event)

        disconnected: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(event)
            except Exception:
                disconnected.append(websocket)

        if disconnected:
            async with self._lock:
                for websocket in disconnected:
                    self._connections.discard(websocket)

    async def is_empty(self) -> bool:
        async with self._lock:
            return not self._connections and not self._subscribers
