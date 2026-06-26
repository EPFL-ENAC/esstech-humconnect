from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import ValidationError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession

from api.db import get_engine, get_session
from api.models.chat import (
    ChatErrorEvent,
    ChatSession,
    ChatSnapshotResponse,
    CreateChatRequest,
    CreateChatResponse,
    ListChatsResponse,
    Message,
    MessageCreatedEvent,
    UserMessageEvent,
    utc_now,
)
from api.services.chat import (
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
    MESSAGE_STATUS_COMPLETE,
    MESSAGE_STATUS_STREAMING,
    build_chat_snapshot,
    chat_stream_manager,
    get_chat_for_client,
    mark_stale_streaming_messages_interrupted,
    serialize_chat,
    serialize_message,
)

router = APIRouter(prefix="/chats", tags=["Chats"])


@router.post("", response_model=CreateChatResponse)
async def create_chat(
    payload: CreateChatRequest,
    session: AsyncSQLModelSession = Depends(get_session),
) -> CreateChatResponse:
    chat = ChatSession(client_id=payload.client_id)
    session.add(chat)
    await session.commit()
    await session.refresh(chat)
    return CreateChatResponse(id=chat.id)


@router.get("", response_model=ListChatsResponse)
async def list_chats(
    client_id: str = Query(min_length=1, max_length=256),
    session: AsyncSQLModelSession = Depends(get_session),
) -> ListChatsResponse:
    result = await session.exec(
        select(ChatSession)
        .where(ChatSession.client_id == client_id)
        .order_by(col(ChatSession.updated_at).desc())
    )
    return ListChatsResponse(chats=[serialize_chat(chat) for chat in result.all()])


@router.get("/{chat_id}", response_model=ChatSnapshotResponse)
async def get_chat(
    chat_id: UUID,
    client_id: str = Query(min_length=1, max_length=256),
    session: AsyncSQLModelSession = Depends(get_session),
) -> ChatSnapshotResponse:
    chat = await get_chat_for_client(session, chat_id, client_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    return await build_chat_snapshot(session, chat)


@router.websocket("/{chat_id}/ws")
async def chat_websocket(
    websocket: WebSocket,
    chat_id: UUID,
    client_id: str = Query(default=""),
) -> None:
    if not client_id:
        await websocket.close(code=1008)
        return

    async with AsyncSQLModelSession(get_engine()) as session:
        chat = await get_chat_for_client(session, chat_id, client_id)
        if chat is None:
            await websocket.close(code=1008)
            return

    await chat_stream_manager.connect(chat_id, websocket)
    try:
        async with AsyncSQLModelSession(get_engine()) as session:
            chat = await get_chat_for_client(session, chat_id, client_id)
            if chat is not None:
                snapshot = await build_chat_snapshot(session, chat)
                await websocket.send_json(snapshot.model_dump(mode="json"))

        while True:
            payload = await websocket.receive_json()
            try:
                client_event = UserMessageEvent.model_validate(payload)
            except ValidationError:
                await websocket.send_json(
                    ChatErrorEvent(message="Unsupported message type.").model_dump(
                        mode="json"
                    )
                )
                continue

            content = client_event.content.strip()
            if not content:
                await websocket.send_json(
                    ChatErrorEvent(message="Message content is required.").model_dump(
                        mode="json"
                    )
                )
                continue

            if await chat_stream_manager.has_active_generation(chat_id):
                await websocket.send_json(
                    ChatErrorEvent(
                        message="Wait for the current response to finish."
                    ).model_dump(mode="json")
                )
                continue

            async with AsyncSQLModelSession(get_engine()) as session:
                chat = await get_chat_for_client(session, chat_id, client_id)
                if chat is None:
                    await websocket.close(code=1008)
                    return

                user_message = Message(
                    chat_id=chat.id,
                    role=MESSAGE_ROLE_USER,
                    content=content,
                    status=MESSAGE_STATUS_COMPLETE,
                )
                assistant_message = Message(
                    chat_id=chat.id,
                    role=MESSAGE_ROLE_ASSISTANT,
                    content="",
                    status=MESSAGE_STATUS_STREAMING,
                )
                chat.title = chat.title or content[:80]
                chat.updated_at = utc_now()
                session.add(chat)
                session.add(user_message)
                session.add(assistant_message)
                await session.commit()
                await session.refresh(user_message)
                await session.refresh(assistant_message)

            await chat_stream_manager.broadcast(
                chat_id,
                MessageCreatedEvent(
                    message=serialize_message(user_message),
                ).model_dump(mode="json"),
            )
            await chat_stream_manager.broadcast(
                chat_id,
                MessageCreatedEvent(
                    message=serialize_message(assistant_message),
                ).model_dump(mode="json"),
            )
            await chat_stream_manager.start_placeholder_generation(
                chat_id=chat_id,
                assistant_message_id=assistant_message.id,
            )
    except WebSocketDisconnect:
        pass
    finally:
        await chat_stream_manager.disconnect(chat_id, websocket)


async def mark_interrupted_messages_on_startup() -> None:
    async with AsyncSQLModelSession(get_engine()) as session:
        await mark_stale_streaming_messages_interrupted(session)
