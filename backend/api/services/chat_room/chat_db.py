import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession

from api.db import get_engine
from api.models.chat import (
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
    MESSAGE_STATUS_COMPLETE,
    MESSAGE_STATUS_ERROR,
    MESSAGE_STATUS_INTERRUPTED,
    MESSAGE_STATUS_STREAMING,
    ChatMessageResponse,
    ChatSession,
    ChatSessionResponse,
    ChatSnapshotResponse,
    Message,
    MessageChunkType,
    ToolCallPayload,
    utc_now,
)

STREAM_COMMIT_TOKEN_BATCH_SIZE = 32
STREAM_COMMIT_INTERVAL_SECONDS = 1.0

ActiveGenerationChecker = Callable[[UUID], Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class ResponseProgressResult:
    chunk_index: int


class PersistentChatMessagesHistory:
    def __init__(
        self,
        chat_id: UUID,
        *,
        has_active_generation: ActiveGenerationChecker | None = None,
    ) -> None:
        self.chat_id = chat_id
        self._has_active_generation = has_active_generation
        self._chat: ChatSessionResponse | None = None
        self._messages: list[ChatMessageResponse] = []
        self._active_assistant_message_id: UUID | None = None
        self._persisted_message_ids: set[UUID] = set()
        self._last_commit_at = 0.0
        self._tokens_since_commit = 0
        self._load_lock = asyncio.Lock()

    async def client_has_access(self, client_id: str) -> bool:
        return await self._ensure_loaded(client_id)

    async def build_snapshot(self, client_id: str) -> ChatSnapshotResponse | None:
        if not await self._ensure_loaded(client_id):
            return None

        if self._chat is None:
            return None

        return ChatSnapshotResponse(
            chat=self._chat,
            messages=list(self._messages),
        )

    async def get_assistant_chat_history(self) -> list[ChatMessageResponse]:
        await self._ensure_loaded()
        return [
            message
            for message in self._messages
            if message.status == MESSAGE_STATUS_COMPLETE
        ]

    async def submit_question(
        self, client_id: str, question: str
    ) -> ChatMessageResponse:
        if not await self._ensure_loaded(client_id):
            raise PermissionError("Chat not found")

        async with AsyncSQLModelSession(
            get_engine(), expire_on_commit=False
        ) as session:
            chat = await get_chat_for_client(session, self.chat_id, client_id)
            if chat is None:
                raise PermissionError("Chat not found")

            user_message = Message.create_user_message(chat.id, question)
            chat.update_title(chat.title or question[:80])

            session.add(chat)
            session.add(user_message)

            await session.commit()
            await session.refresh(chat)
            await session.refresh(user_message)

        user_response = ChatMessageResponse.from_db_model(user_message)
        self._chat = ChatSessionResponse.from_db_model(chat)
        self._messages.append(user_response)
        self._persisted_message_ids.add(user_response.id)

        self._tokens_since_commit = 0
        self._last_commit_at = asyncio.get_running_loop().time()

        return user_response

    async def start_response(self) -> ChatMessageResponse:
        await self._ensure_loaded()

        message = self._active_assistant_message
        if message is not None and message.status == MESSAGE_STATUS_STREAMING:
            return message

        message = ChatMessageResponse.make_assistant_message(self.chat_id)
        self._messages.append(message)
        self._active_assistant_message_id = message.id
        await self._insert_active_message()
        return message

    async def response_progress(
        self, chunk_index: int, chunk_type: MessageChunkType, delta: str
    ) -> ResponseProgressResult | None:
        message = self._active_assistant_message
        if message is None:
            return None
        elif message.status != MESSAGE_STATUS_STREAMING:
            return None
        else:
            message.append_chunk_delta(chunk_index, chunk_type, delta)

        self._tokens_since_commit += len(delta)

        if message.id not in self._persisted_message_ids:
            await self._insert_active_message()
            return ResponseProgressResult(chunk_index=chunk_index)

        if self._should_commit():
            await self._commit_active_message_chunks()
        return ResponseProgressResult(chunk_index=chunk_index)

    async def response_payload_update(
        self, chunk_index: int, chunk_type: MessageChunkType, payload: ToolCallPayload
    ) -> ResponseProgressResult | None:
        message = self._active_assistant_message
        if message is None:
            return None
        elif message.status != MESSAGE_STATUS_STREAMING:
            return None
        else:
            message.update_chunk_payload(chunk_index, chunk_type, payload)

        if message.id not in self._persisted_message_ids:
            await self._insert_active_message()
            return ResponseProgressResult(chunk_index=chunk_index)

        await self._commit_active_message_chunks()
        return ResponseProgressResult(chunk_index=chunk_index)

    async def complete_response(self) -> None:
        message = self._active_assistant_message
        if message is None:
            return

        message.status = MESSAGE_STATUS_COMPLETE
        message.updated_at = utc_now()
        async with AsyncSQLModelSession(
            get_engine(), expire_on_commit=False
        ) as session:
            if message.id in self._persisted_message_ids:
                db_message = await session.get(Message, message.id)

                if db_message is not None:
                    db_message.chunks = [
                        chunk.model_dump(mode="json") for chunk in message.chunks
                    ]
                    db_message.status = MESSAGE_STATUS_COMPLETE
                    db_message.updated_at = message.updated_at
                    session.add(db_message)

            chat = await session.get(ChatSession, self.chat_id)
            if chat is not None:
                chat.updated_at = utc_now()
                session.add(chat)

            await session.commit()
            if chat is not None:
                self._chat = ChatSessionResponse.from_db_model(chat)

        self._post_commit()
        self._active_assistant_message_id = None

    async def fail_response(self) -> None:
        message = self._active_assistant_message
        if message is None:
            return

        message.update_status(MESSAGE_STATUS_ERROR)

        async with AsyncSQLModelSession(
            get_engine(), expire_on_commit=False
        ) as session:
            if message.id in self._persisted_message_ids:
                db_message = await session.get(Message, message.id)
            else:
                db_message = None

            if db_message is not None:
                db_message.update_chunks_status(message.chunks, MESSAGE_STATUS_ERROR)
                session.add(db_message)
                await session.commit()

        self._post_commit()
        self._active_assistant_message_id = None

    @property
    def active_response_message_id(self) -> UUID | None:
        return self._active_assistant_message_id

    @property
    def _active_assistant_message(self) -> ChatMessageResponse | None:
        if self._active_assistant_message_id is None:
            return None
        for message in reversed(self._messages):
            if message.id == self._active_assistant_message_id:
                return message
        return None

    async def _ensure_loaded(self, client_id: str | None = None) -> bool:
        async with self._load_lock:
            if self._chat is not None:
                return client_id is None or self._chat.client_id == client_id

            async with AsyncSQLModelSession(
                get_engine(), expire_on_commit=False
            ) as session:
                chat = None
                if client_id is None:
                    chat = await session.get(ChatSession, self.chat_id)
                else:
                    chat = await get_chat_for_client(session, self.chat_id, client_id)

                if chat is None:
                    return False

                await mark_stale_streaming_messages_interrupted(
                    session,
                    chat_id=chat.id,
                    has_active_generation=self._has_active_generation,
                )
                messages = await session.exec(
                    select(Message)
                    .where(Message.chat_id == chat.id)
                    .order_by(col(Message.created_at))
                )
                refreshed_chat = await session.get(ChatSession, chat.id)
                self._chat = ChatSessionResponse.from_db_model(refreshed_chat or chat)
                self._messages = [
                    ChatMessageResponse.from_db_model(message)
                    for message in messages.all()
                ]
                self._persisted_message_ids = {message.id for message in self._messages}
                self._active_assistant_message_id = self._find_streaming_assistant_id()
                self._post_commit()
                return True

    def _find_streaming_assistant_id(self) -> UUID | None:
        for message in reversed(self._messages):
            if (
                message.role == MESSAGE_ROLE_ASSISTANT
                and message.status == MESSAGE_STATUS_STREAMING
            ):
                return message.id
        return None

    def _should_commit(self) -> bool:
        now = asyncio.get_running_loop().time()
        return (
            self._tokens_since_commit >= STREAM_COMMIT_TOKEN_BATCH_SIZE
            or now - self._last_commit_at >= STREAM_COMMIT_INTERVAL_SECONDS
        )

    async def _insert_active_message(self) -> None:
        message = self._active_assistant_message
        if message is None:
            return

        async with AsyncSQLModelSession(
            get_engine(), expire_on_commit=False
        ) as session:
            db_message = Message.from_response(message)
            session.add(db_message)
            await session.commit()

        self._persisted_message_ids.add(message.id)
        self._post_commit()

    async def _commit_active_message_chunks(self) -> None:
        message = self._active_assistant_message
        if message is None:
            return

        async with AsyncSQLModelSession(
            get_engine(), expire_on_commit=False
        ) as session:
            db_message = await session.get(Message, message.id)
            if db_message is None:
                return
            db_message.chunks = [
                chunk.model_dump(mode="json") for chunk in message.chunks
            ]
            db_message.updated_at = message.updated_at
            session.add(db_message)
            await session.commit()

        self._post_commit()

    def _post_commit(self):
        self._tokens_since_commit = 0
        self._last_commit_at = asyncio.get_running_loop().time()


async def get_chat_for_client(
    session: AsyncSQLModelSession, chat_id: UUID, client_id: str
) -> ChatSession | None:
    result = await session.exec(
        select(ChatSession).where(
            ChatSession.id == chat_id,
            ChatSession.client_id == client_id,
        )
    )
    return result.first()


async def mark_stale_streaming_messages_interrupted(
    session: AsyncSQLModelSession,
    *,
    chat_id: UUID | None = None,
    has_active_generation: ActiveGenerationChecker | None = None,
) -> None:
    query = select(Message).where(Message.status == MESSAGE_STATUS_STREAMING)
    if chat_id is not None:
        query = query.where(Message.chat_id == chat_id)

    result = await session.exec(query)
    messages = result.all()
    changed_messages = False
    for message in messages:
        message_chat_id = chat_id or message.chat_id
        if has_active_generation is not None and await has_active_generation(
            message_chat_id
        ):
            continue

        message.status = MESSAGE_STATUS_INTERRUPTED
        message.updated_at = utc_now()
        session.add(message)
        changed_messages = True

    if changed_messages:
        await session.commit()


async def build_chat_snapshot(
    session: AsyncSQLModelSession,
    chat: ChatSession,
    *,
    has_active_generation: ActiveGenerationChecker | None = None,
) -> ChatSnapshotResponse:
    await mark_stale_streaming_messages_interrupted(
        session,
        chat_id=chat.id,
        has_active_generation=has_active_generation,
    )

    messages = await session.exec(
        select(Message)
        .where(Message.chat_id == chat.id)
        .order_by(col(Message.created_at))
    )
    refreshed_chat = await session.get(ChatSession, chat.id)
    return ChatSnapshotResponse(
        chat=ChatSessionResponse.from_db_model(refreshed_chat or chat),
        messages=[
            ChatMessageResponse.from_db_model(message) for message in messages.all()
        ],
    )
