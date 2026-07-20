from typing import Annotated

from enacit4r_auth.services.auth import User
from fastapi import APIRouter, Depends, Query
from sqlalchemy import Text, cast, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession

from api.auth import require_admin
from api.db import get_session
from api.models.recorded_event import (
    EventTag,
    ListRecordedEventsFilters,
    ListRecordedEventsResponse,
    RecordedEvent,
    RecordedEventResponse,
)
from api.models.user_profile import ProfessionCategory
from api.utils.pydantic_types import NonEmptyString

router = APIRouter(prefix="/recorded-events", tags=["Recorded events"])


def get_recorded_event_filters(
    keyword: Annotated[NonEmptyString | None, Query()] = None,
    tags: Annotated[list[EventTag] | None, Query()] = None,
    affected_profession_categories: Annotated[
        list[ProfessionCategory] | None,
        Query(),
    ] = None,
    response_profession_categories: Annotated[
        list[ProfessionCategory] | None,
        Query(),
    ] = None,
) -> ListRecordedEventsFilters:
    return ListRecordedEventsFilters(
        keyword=keyword,
        tags=tags or [],
        affected_profession_categories=affected_profession_categories or [],
        response_profession_categories=response_profession_categories or [],
    )


@router.get("", response_model=ListRecordedEventsResponse)
async def list_recorded_events(
    filters: Annotated[ListRecordedEventsFilters, Depends(get_recorded_event_filters)],
    user: User = Depends(require_admin()),
    session: AsyncSQLModelSession = Depends(get_session),
) -> ListRecordedEventsResponse:
    query = select(RecordedEvent).order_by(col(RecordedEvent.created_at).desc())

    if filters.keyword is not None:
        query = query.where(
            cast(RecordedEvent.keywords, Text).ilike(f"%{filters.keyword}%")
        )

    if filters.tags:
        tags_jsonb = col(RecordedEvent.tags)
        query = query.where(or_(*(tags_jsonb.contains([tag]) for tag in filters.tags)))

    if filters.affected_profession_categories:
        affected_jsonb = col(RecordedEvent.affected_profession_categories)
        query = query.where(
            or_(
                *(
                    affected_jsonb.contains([category])
                    for category in filters.affected_profession_categories
                )
            )
        )

    if filters.response_profession_categories:
        response_jsonb = col(RecordedEvent.response_profession_categories)
        query = query.where(
            or_(
                *(
                    response_jsonb.contains([category])
                    for category in filters.response_profession_categories
                )
            )
        )

    result = await session.exec(query)
    return ListRecordedEventsResponse(
        events=[RecordedEventResponse.model_validate(event) for event in result.all()]
    )
