import asyncio
from uuid import UUID

from api.services.chat_room.chat_room import ChatRoomService


class ChatRoomRegistry:
    def __init__(self) -> None:
        self._rooms: dict[UUID, ChatRoomService] = {}
        self._lock = asyncio.Lock()

    async def get_room(self, chat_id: UUID) -> ChatRoomService:
        async with self._lock:
            room = self._rooms.get(chat_id)
            if room is None:
                room = ChatRoomService(
                    chat_id,
                    has_active_generation=self.has_active_generation,
                )
                self._rooms[chat_id] = room
            return room

    async def release_room(self, chat_id: UUID) -> None:
        async with self._lock:
            room = self._rooms.get(chat_id)
            if room is not None and await room.is_idle():
                self._rooms.pop(chat_id, None)

    async def has_active_generation(self, chat_id: UUID) -> bool:
        async with self._lock:
            room = self._rooms.get(chat_id)
        return room is not None and await room.has_active_generation()


chat_room_registry = ChatRoomRegistry()
