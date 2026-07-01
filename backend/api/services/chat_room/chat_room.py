import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from uuid import UUID

from api.models.chat import (
    ChatMessageResponse,
    ChatSnapshotResponse,
    MessageChunkType,
    MessageCreatedEvent,
    MessageDeltaEvent,
    MessageDoneEvent,
    MessageStatus,
    MessageUpdatePayloadEvent,
    ToolCallPayload,
)
from api.services.chat_room.chat_assistant import (
    AssistantStreamChunkDelta,
    AssistantStreamPayloadUpdate,
    ChatAssistant,
)
from api.services.chat_room.chat_db import (
    MESSAGE_STATUS_COMPLETE,
    MESSAGE_STATUS_ERROR,
    PersistentChatMessagesHistory,
)
from api.services.chat_room.humconnect_assistant import HumConnectAssistant
from api.services.chat_room.tools.base import ToolExecutionContext

logger = logging.getLogger("uvicorn.error")


class ChatRoomService:
    def __init__(
        self,
        chat_id: UUID,
        *,
        messages_history: PersistentChatMessagesHistory | None = None,
        chat_assistant: ChatAssistant | None = None,
    ) -> None:
        self.chat_id = chat_id
        self._subscribers: set[asyncio.Queue[dict | None]] = set()
        self._messages_history = messages_history or PersistentChatMessagesHistory(
            chat_id
        )
        self._chat_assistant = chat_assistant or HumConnectAssistant()
        self._generation_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._submission_lock = asyncio.Lock()

    async def broadcast(self, event: dict) -> None:
        for queue in list(self._subscribers):
            queue.put_nowait(event)

    async def subscribe(
        self,
        user_id: UUID | None = None,
        *,
        with_snapshot: bool = False,
    ) -> AsyncIterator[dict]:
        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            if with_snapshot:
                if user_id is None:
                    raise ValueError("user_id is required when with_snapshot is true")

                snapshot = await self.build_snapshot(user_id)
                if snapshot is None:
                    return
                yield snapshot.model_dump(mode="json")

            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            self._subscribers.discard(queue)

    async def has_active_generation(self) -> bool:
        async with self._lock:
            return self._has_active_generation_locked()

    async def is_idle(self) -> bool:
        return not self._subscribers and not await self.has_active_generation()

    async def verify_user_access(self, user_id: UUID) -> bool:
        return await self._messages_history.user_has_access(user_id)

    async def build_snapshot(self, user_id: UUID) -> ChatSnapshotResponse | None:
        return await self._messages_history.build_snapshot(
            user_id,
            interrupt_stale_streaming_messages=not await self.has_active_generation(),
        )

    async def handle_user_message(self, user_id: UUID, content: str) -> None:
        async with self._submission_lock:
            await self._ensure_no_active_response()
            chat_history = await self._messages_history.get_assistant_chat_history()
            user_message = await self._messages_history.submit_question(
                user_id, content
            )

            # broadcast the question
            await self.broadcast(
                MessageCreatedEvent(
                    message=user_message,
                ).model_dump(mode="json"),
            )

            await self._start_assistant_response(
                chat_history,
                content,
                ToolExecutionContext(
                    chat_id=self.chat_id,
                    user_id=user_id,
                    source_message_id=user_message.id,
                ),
            )

    async def _ensure_no_active_response(self) -> None:
        if await self.has_active_generation():
            raise RuntimeError("A response is already streaming for this chat.")

    async def _start_assistant_response(
        self,
        chat_history: Sequence[ChatMessageResponse],
        question: str,
        tool_context: ToolExecutionContext | None = None,
    ) -> None:
        async with self._lock:
            if self._has_active_generation_locked():
                raise RuntimeError("A response is already streaming for this chat.")

            assistant_message = await self._messages_history.start_response()
            await self.broadcast(
                MessageCreatedEvent(
                    message=assistant_message,
                ).model_dump(mode="json"),
            )

            self._generation_task = asyncio.create_task(
                self._stream_assistant_response(
                    chat_history,
                    question,
                    tool_context,
                )
            )

    async def _stream_assistant_response(
        self,
        chat_history: Sequence[ChatMessageResponse] | None = None,
        question: str = "",
        tool_context: ToolExecutionContext | None = None,
    ) -> None:
        try:
            try:
                await self._push_assistant_response_stream(
                    chat_history or [],
                    question,
                    tool_context,
                )
            except Exception as e:
                logger.exception(
                    "Error during assistant response streaming: %s",
                    e,
                )
                await self._fail_assistant_response()
                return

            assistant_message_id = self._messages_history.active_response_message_id
            if assistant_message_id is None:
                return
            try:
                await self._messages_history.complete_response()
            except Exception as e:
                logger.exception(
                    "Error during assistant response completion: %s",
                    e,
                )
                await self._fail_assistant_response()
                return
            await self._broadcast_assistant_response_done(
                assistant_message_id, MESSAGE_STATUS_COMPLETE
            )
        finally:
            current_task = asyncio.current_task()
            async with self._lock:
                if self._generation_task is current_task:
                    self._generation_task = None

    async def _push_assistant_response_stream(
        self,
        chat_history: Sequence[ChatMessageResponse],
        question: str,
        tool_context: ToolExecutionContext | None,
    ) -> None:
        async for chunk in self._chat_assistant.stream_response(
            chat_history,
            question,
            tool_context,
        ):
            if isinstance(chunk, AssistantStreamChunkDelta):
                progress = await self._messages_history.response_progress(
                    chunk.index, chunk.type, chunk.content_delta
                )
                assistant_message_id = self._messages_history.active_response_message_id
                if assistant_message_id is None or progress is None:
                    continue
                await self._broadcast_assistant_response_delta(
                    assistant_message_id,
                    progress.chunk_index,
                    chunk.type,
                    chunk.content_delta,
                )
            elif isinstance(chunk, AssistantStreamPayloadUpdate):
                progress = await self._messages_history.response_payload_update(
                    chunk.index, chunk.type, chunk.payload
                )
                assistant_message_id = self._messages_history.active_response_message_id
                if assistant_message_id is None or progress is None:
                    continue
                await self._broadcast_assistant_response_payload_update(
                    assistant_message_id,
                    progress.chunk_index,
                    chunk.type,
                    chunk.payload,
                )

    async def _broadcast_assistant_response_delta(
        self,
        assistant_message_id: UUID,
        chunk_index: int,
        chunk_type: MessageChunkType,
        delta: str,
    ) -> None:
        await self.broadcast(
            MessageDeltaEvent(
                message_id=assistant_message_id,
                chunk_index=chunk_index,
                chunk_type=chunk_type,
                delta=delta,
            ).model_dump(mode="json"),
        )

    async def _broadcast_assistant_response_payload_update(
        self,
        assistant_message_id: UUID,
        chunk_index: int,
        chunk_type: MessageChunkType,
        payload: ToolCallPayload,
    ) -> None:
        await self.broadcast(
            MessageUpdatePayloadEvent(
                message_id=assistant_message_id,
                chunk_index=chunk_index,
                chunk_type=chunk_type,
                payload=payload,
            ).model_dump(mode="json"),
        )

    async def _fail_assistant_response(self) -> None:
        assistant_message_id = self._messages_history.active_response_message_id
        if assistant_message_id is None:
            return
        await self._messages_history.fail_response()
        await self._broadcast_assistant_response_done(
            assistant_message_id, MESSAGE_STATUS_ERROR
        )

    async def _broadcast_assistant_response_done(
        self, assistant_message_id: UUID, status: MessageStatus
    ) -> None:
        await self.broadcast(
            MessageDoneEvent(
                message_id=assistant_message_id,
                status=status,
            ).model_dump(mode="json"),
        )

    def _has_active_generation_locked(self) -> bool:
        task = self._generation_task
        return task is not None and not task.done()
