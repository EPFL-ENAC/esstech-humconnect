from fastapi import APIRouter, Depends
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession

from api.db import get_session
from api.models.recorded_event import (
    ListRecordedEventsResponse,
    RecordedEvent,
    RecordedEventResponse,
)

router = APIRouter(prefix="/recorded-events", tags=["Recorded events"])


@router.get("", response_model=ListRecordedEventsResponse)
async def list_recorded_events(
    session: AsyncSQLModelSession = Depends(get_session),
) -> ListRecordedEventsResponse:
    result = await session.exec(
        select(RecordedEvent).order_by(col(RecordedEvent.created_at).desc())
    )
    return ListRecordedEventsResponse(
        events=[RecordedEventResponse.model_validate(event) for event in result.all()]
    )
