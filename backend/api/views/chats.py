import json
from collections.abc import AsyncIterator
from uuid import UUID

from enacit4r_auth.services.auth import User
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession
from starlette.requests import ClientDisconnect
from starlette.responses import StreamingResponse

from api.auth import require_user
from api.db import get_engine, get_session
from api.models.chat import (
    ChatSession,
    ChatSessionResponse,
    ChatSnapshotResponse,
    CreateChatMessageRequest,
    CreateChatResponse,
    ListChatsResponse,
)
from api.services.chat import (
    chat_room_registry,
    mark_stale_streaming_messages_interrupted,
)
from api.services.user_profiles import get_or_create_user_profile_from_token

router = APIRouter(prefix="/chats", tags=["Chats"])


@router.post("", response_model=CreateChatResponse)
async def create_chat(
    user: User = Depends(require_user()),
    session: AsyncSQLModelSession = Depends(get_session),
) -> CreateChatResponse:
    profile = await get_or_create_user_profile_from_token(user, session)
    chat = ChatSession(user_id=profile.id)
    session.add(chat)
    await session.commit()
    await session.refresh(chat)
    return CreateChatResponse(id=chat.id)


@router.get("", response_model=ListChatsResponse)
async def list_chats(
    user: User = Depends(require_user()),
    session: AsyncSQLModelSession = Depends(get_session),
) -> ListChatsResponse:
    profile = await get_or_create_user_profile_from_token(user, session)
    result = await session.exec(
        select(ChatSession)
        .where(ChatSession.user_id == profile.id)
        .order_by(col(ChatSession.updated_at).desc())
    )
    return ListChatsResponse(
        chats=[ChatSessionResponse.from_db_model(chat) for chat in result.all()]
    )


@router.get("/{chat_id}", response_model=ChatSnapshotResponse)
async def get_chat(
    chat_id: UUID,
    user: User = Depends(require_user()),
    session: AsyncSQLModelSession = Depends(get_session),
) -> ChatSnapshotResponse:
    profile = await get_or_create_user_profile_from_token(user, session)
    room = await chat_room_registry.get_room(chat_id)
    try:
        snapshot = await room.build_snapshot(profile.id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Chat not found")

        return snapshot
    finally:
        await chat_room_registry.release_room_if_idle(chat_id)


@router.post("/{chat_id}/messages", status_code=status.HTTP_202_ACCEPTED)
async def create_chat_message(
    chat_id: UUID,
    payload: CreateChatMessageRequest,
    user: User = Depends(require_user()),
    session: AsyncSQLModelSession = Depends(get_session),
) -> Response:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message content is required.")

    profile = await get_or_create_user_profile_from_token(user, session)
    room = await chat_room_registry.get_room(chat_id)
    try:
        if not await room.verify_user_access(profile.id):
            raise HTTPException(status_code=404, detail="Chat not found")

        if await room.has_active_generation():
            raise HTTPException(
                status_code=409,
                detail="Wait for the current response to finish.",
            )

        try:
            await room.handle_user_message(profile.id, content)
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
    user: User = Depends(require_user()),
    session: AsyncSQLModelSession = Depends(get_session),
) -> StreamingResponse:
    profile = await get_or_create_user_profile_from_token(user, session)
    room = await chat_room_registry.get_room(chat_id)
    if not await room.verify_user_access(profile.id):
        await chat_room_registry.release_room_if_idle(chat_id)
        raise HTTPException(status_code=404, detail="Chat not found")

    async def stream_events() -> AsyncIterator[str]:
        try:
            async for event in room.subscribe(profile.id, with_snapshot=True):
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
