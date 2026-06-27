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
    ChatSessionResponse,
    ChatSnapshotResponse,
    CreateChatRequest,
    CreateChatResponse,
    ListChatsResponse,
    UserMessageEvent,
)
from api.services.chat import (
    chat_room_registry,
    mark_stale_streaming_messages_interrupted,
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
    return ListChatsResponse(
        chats=[ChatSessionResponse.from_db_model(chat) for chat in result.all()]
    )


@router.get("/{chat_id}", response_model=ChatSnapshotResponse)
async def get_chat(
    chat_id: UUID,
    client_id: str = Query(min_length=1, max_length=256),
) -> ChatSnapshotResponse:
    room = await chat_room_registry.get_room(chat_id)
    try:
        snapshot = await room.build_snapshot(client_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Chat not found")

        return snapshot
    finally:
        await chat_room_registry.release_room(chat_id)


@router.websocket("/{chat_id}/ws")
async def chat_websocket(
    websocket: WebSocket,
    chat_id: UUID,
    client_id: str = Query(default=""),
) -> None:
    if not client_id:
        await websocket.close(code=1008)
        return

    room = await chat_room_registry.get_room(chat_id)
    if not await room.verify_client_access(client_id):
        await websocket.close(code=1008)
        await chat_room_registry.release_room(chat_id)
        return

    await room.connect(websocket)
    try:
        snapshot = await room.build_snapshot(client_id)
        if snapshot is None:
            await websocket.close(code=1008)
            return
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

            if await room.has_active_generation():
                await websocket.send_json(
                    ChatErrorEvent(
                        message="Wait for the current response to finish."
                    ).model_dump(mode="json")
                )
                continue

            try:
                await room.handle_user_message(client_id, content)
            except PermissionError:
                await websocket.close(code=1008)
                return
            except RuntimeError:
                await websocket.send_json(
                    ChatErrorEvent(
                        message="Wait for the current response to finish."
                    ).model_dump(mode="json")
                )
    except WebSocketDisconnect:
        pass
    finally:
        await room.disconnect(websocket)
        await chat_room_registry.release_room(chat_id)


async def mark_interrupted_messages_on_startup() -> None:
    async with AsyncSQLModelSession(get_engine()) as session:
        await mark_stale_streaming_messages_interrupted(session)
