import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class ChatRoomConnectionHub:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict | None]] = set()
        self._lock = asyncio.Lock()

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
            subscribers = list(self._subscribers)

        for queue in subscribers:
            queue.put_nowait(event)

    async def is_empty(self) -> bool:
        async with self._lock:
            return not self._subscribers
