import asyncio
import random
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession

from api.db import get_engine
from api.models.chat import ChatSession, Message, utc_now

MESSAGE_ROLE_ASSISTANT = "assistant"
MESSAGE_ROLE_USER = "user"

MESSAGE_STATUS_COMPLETE = "complete"
MESSAGE_STATUS_ERROR = "error"
MESSAGE_STATUS_INTERRUPTED = "interrupted"
MESSAGE_STATUS_STREAMING = "streaming"

STREAM_COMMIT_TOKEN_BATCH_SIZE = 32
STREAM_COMMIT_INTERVAL_SECONDS = 1.0


class ChatStreamManager:
    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = defaultdict(set)
        self._tasks: dict[UUID, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def connect(self, chat_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[chat_id].add(websocket)

    async def disconnect(self, chat_id: UUID, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(chat_id)
            if sockets is None:
                return
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(chat_id, None)

    async def broadcast(self, chat_id: UUID, event: dict) -> None:
        async with self._lock:
            sockets = list(self._connections.get(chat_id, set()))

        disconnected: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(event)
            except Exception:
                disconnected.append(websocket)

        if disconnected:
            async with self._lock:
                for websocket in disconnected:
                    self._connections.get(chat_id, set()).discard(websocket)

    async def has_active_generation(self, chat_id: UUID) -> bool:
        async with self._lock:
            task = self._tasks.get(chat_id)
            return task is not None and not task.done()

    async def start_placeholder_generation(
        self,
        *,
        chat_id: UUID,
        assistant_message_id: UUID,
    ) -> None:
        async with self._lock:
            task = self._tasks.get(chat_id)
            if task is not None and not task.done():
                raise RuntimeError("A response is already streaming for this chat.")

            self._tasks[chat_id] = asyncio.create_task(
                self._stream_placeholder_response(chat_id, assistant_message_id)
            )

    async def _stream_placeholder_response(
        self, chat_id: UUID, assistant_message_id: UUID
    ) -> None:
        try:
            random_number = random.randint(0, 999999)
            response = f"Random number: {random_number}"

            async with AsyncSQLModelSession(
                get_engine(), expire_on_commit=False
            ) as session:
                message = await session.get(Message, assistant_message_id)
                if message is None:
                    return

                chat = await session.get(ChatSession, chat_id)
                loop = asyncio.get_running_loop()
                last_commit_at = loop.time()
                tokens_since_commit = 0
                response_length = len(response)

                for token_index, token in enumerate(response, start=1):
                    message.content += token
                    message.updated_at = utc_now()
                    tokens_since_commit += 1

                    await self.broadcast(
                        chat_id,
                        {
                            "type": "message_delta",
                            "message_id": str(assistant_message_id),
                            "delta": token,
                        },
                    )

                    now = loop.time()
                    should_commit_batch = (
                        tokens_since_commit >= STREAM_COMMIT_TOKEN_BATCH_SIZE
                        or now - last_commit_at >= STREAM_COMMIT_INTERVAL_SECONDS
                    )
                    if should_commit_batch and token_index < response_length:
                        session.add(message)
                        await session.commit()
                        tokens_since_commit = 0
                        last_commit_at = now

                    await asyncio.sleep(0.05)

                message.status = MESSAGE_STATUS_COMPLETE
                message.updated_at = utc_now()
                session.add(message)
                if chat is not None:
                    chat.updated_at = utc_now()
                    session.add(chat)
                await session.commit()

            await self.broadcast(
                chat_id,
                {
                    "type": "message_done",
                    "message_id": str(assistant_message_id),
                    "status": MESSAGE_STATUS_COMPLETE,
                },
            )
        except Exception:
            async with AsyncSQLModelSession(get_engine()) as session:
                message = await session.get(Message, assistant_message_id)
                if message is not None:
                    message.status = MESSAGE_STATUS_ERROR
                    message.updated_at = utc_now()
                    session.add(message)
                    await session.commit()

            await self.broadcast(
                chat_id,
                {
                    "type": "message_done",
                    "message_id": str(assistant_message_id),
                    "status": MESSAGE_STATUS_ERROR,
                },
            )
        finally:
            current_task = asyncio.current_task()
            async with self._lock:
                task = self._tasks.get(chat_id)
                if task is current_task:
                    self._tasks.pop(chat_id, None)


chat_stream_manager = ChatStreamManager()


def serialize_chat(chat: ChatSession) -> dict:
    return {
        "id": str(chat.id),
        "client_id": chat.client_id,
        "title": chat.title,
        "created_at": chat.created_at.isoformat(),
        "updated_at": chat.updated_at.isoformat(),
    }


def serialize_message(message: Message) -> dict:
    return {
        "id": str(message.id),
        "chat_id": str(message.chat_id),
        "role": message.role,
        "content": message.content,
        "status": message.status,
        "created_at": message.created_at.isoformat(),
        "updated_at": message.updated_at.isoformat(),
    }


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
) -> None:
    query = select(Message).where(Message.status == MESSAGE_STATUS_STREAMING)
    if chat_id is not None:
        query = query.where(Message.chat_id == chat_id)

    result = await session.exec(query)
    messages = result.all()
    changed_messages = False
    for message in messages:
        if chat_id is not None and await chat_stream_manager.has_active_generation(
            chat_id
        ):
            continue
        if chat_id is None and await chat_stream_manager.has_active_generation(
            message.chat_id
        ):
            continue
        message.status = MESSAGE_STATUS_INTERRUPTED
        message.updated_at = utc_now()
        session.add(message)
        changed_messages = True

    if changed_messages:
        await session.commit()


async def build_chat_snapshot(session: AsyncSQLModelSession, chat: ChatSession) -> dict:
    await mark_stale_streaming_messages_interrupted(session, chat_id=chat.id)

    messages = await session.exec(
        select(Message)
        .where(Message.chat_id == chat.id)
        .order_by(col(Message.created_at))
    )
    refreshed_chat = await session.get(ChatSession, chat.id)
    return {
        "type": "snapshot",
        "chat": serialize_chat(refreshed_chat or chat),
        "messages": [serialize_message(message) for message in messages.all()],
    }
