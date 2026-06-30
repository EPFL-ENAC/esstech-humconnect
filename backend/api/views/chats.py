import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession
from starlette.requests import ClientDisconnect
from starlette.responses import StreamingResponse

from api.db import get_engine, get_session
from api.models.chat import (
    ChatSession,
    ChatSessionResponse,
    ChatSnapshotResponse,
    CreateChatMessageRequest,
    CreateChatRequest,
    CreateChatResponse,
    ListChatsResponse,
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
        await chat_room_registry.release_room_if_idle(chat_id)


@router.post("/{chat_id}/messages", status_code=status.HTTP_202_ACCEPTED)
async def create_chat_message(
    chat_id: UUID,
    payload: CreateChatMessageRequest,
) -> Response:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message content is required.")

    room = await chat_room_registry.get_room(chat_id)
    try:
        if not await room.verify_client_access(payload.client_id):
            raise HTTPException(status_code=404, detail="Chat not found")

        if await room.has_active_generation():
            raise HTTPException(
                status_code=409,
                detail="Wait for the current response to finish.",
            )

        try:
            await room.handle_user_message(payload.client_id, content)
        except PermissionError:
            raise HTTPException(status_code=404, detail="Chat not found") from None
        except RuntimeError:
            raise HTTPException(
                status_code=409,
                detail="Wait for the current response to finish.",
            ) from None
    finally:
        await chat_room_registry.release_room_if_idle(chat_id)

    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get("/{chat_id}/events")
async def chat_events(
    chat_id: UUID,
    client_id: str = Query(min_length=1, max_length=256),
) -> StreamingResponse:
    room = await chat_room_registry.get_room(chat_id)
    if not await room.verify_client_access(client_id):
        await chat_room_registry.release_room_if_idle(chat_id)
        raise HTTPException(status_code=404, detail="Chat not found")

    async def stream_events() -> AsyncIterator[str]:
        try:
            async for event in room.subscribe(client_id, with_snapshot=True):
                yield _format_sse_event(event)
        except ClientDisconnect:
            return
        finally:
            await chat_room_registry.release_room_if_idle(chat_id)

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _format_sse_event(event: dict) -> str:
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


async def mark_interrupted_messages_on_startup() -> None:
    async with AsyncSQLModelSession(get_engine()) as session:
        await mark_stale_streaming_messages_interrupted(session)
