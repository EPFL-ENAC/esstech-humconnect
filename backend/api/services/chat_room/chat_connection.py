import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class ChatRoomConnectionHub:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict | None]] = set()

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict | None]]:
        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    async def broadcast(self, event: dict) -> None:
        for queue in list(self._subscribers):
            queue.put_nowait(event)

    async def is_empty(self) -> bool:
        return not self._subscribers
