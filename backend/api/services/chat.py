from uuid import UUID

from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession

from api.services.chat_registry import ChatRoomRegistry, chat_room_registry
from api.services.chat_room.chat_assistant import (
    ChatAssistant,
    PlaceholderChatAssistant,
)
from api.services.chat_room.chat_db import (
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
    MESSAGE_STATUS_COMPLETE,
    MESSAGE_STATUS_ERROR,
    MESSAGE_STATUS_INTERRUPTED,
    MESSAGE_STATUS_STREAMING,
    STREAM_COMMIT_INTERVAL_SECONDS,
    STREAM_COMMIT_TOKEN_BATCH_SIZE,
    PersistentChatMessagesHistory,
    ResponseProgressResult,
    build_chat_snapshot,
    get_chat_for_client,
)
from api.services.chat_room.chat_db import (
    mark_stale_streaming_messages_interrupted as _mark_stale_streaming_messages_interrupted,
)
from api.services.chat_room.chat_room import ChatRoomService
from api.services.chat_room.humconnect_assistant import HumConnectAssistant


async def mark_stale_streaming_messages_interrupted(
    session: AsyncSQLModelSession,
    *,
    chat_id: UUID | None = None,
) -> None:
    await _mark_stale_streaming_messages_interrupted(
        session,
        chat_id=chat_id,
    )


__all__ = [
    "MESSAGE_ROLE_ASSISTANT",
    "MESSAGE_ROLE_USER",
    "MESSAGE_STATUS_COMPLETE",
    "MESSAGE_STATUS_ERROR",
    "MESSAGE_STATUS_INTERRUPTED",
    "MESSAGE_STATUS_STREAMING",
    "STREAM_COMMIT_INTERVAL_SECONDS",
    "STREAM_COMMIT_TOKEN_BATCH_SIZE",
    "ChatAssistant",
    "ChatRoomRegistry",
    "ChatRoomService",
    "PlaceholderChatAssistant",
    "HumConnectAssistant",
    "PersistentChatMessagesHistory",
    "ResponseProgressResult",
    "build_chat_snapshot",
    "chat_room_registry",
    "get_chat_for_client",
    "mark_stale_streaming_messages_interrupted",
]
