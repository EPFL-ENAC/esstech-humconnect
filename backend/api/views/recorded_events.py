from typing import Annotated

from enacit4r_auth.services.auth import User
from fastapi import APIRouter, Depends, Query

from api.auth import require_admin
from api.models.recorded_event import (
    EventTag,
    ListRecordedEventsFilters,
    ListRecordedEventsResponse,
    RecordedEventCountryCount,
    RecordedEventCountsByCountryResponse,
    RecordedEventResponse,
)
from api.models.user_profile import ProfessionCategory
from api.services.recorded_events import RecordedEventService
from api.utils.pydantic_types import NonEmptyString

router = APIRouter(prefix="/recorded-events", tags=["Recorded events"])


def get_recorded_event_service() -> RecordedEventService:
    return RecordedEventService()


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
    service: Annotated[
        RecordedEventService,
        Depends(get_recorded_event_service),
    ],
    user: User = Depends(require_admin()),
) -> ListRecordedEventsResponse:
    events = await service.list_events(filters=filters)
    return ListRecordedEventsResponse(
        events=[RecordedEventResponse.from_recorded_event(event) for event in events]
    )


@router.get(
    "/count-by-country",
    response_model=RecordedEventCountsByCountryResponse,
)
async def count_recorded_events_by_country(
    filters: Annotated[ListRecordedEventsFilters, Depends(get_recorded_event_filters)],
    service: Annotated[
        RecordedEventService,
        Depends(get_recorded_event_service),
    ],
    user: User = Depends(require_admin()),
) -> RecordedEventCountsByCountryResponse:
    counts = await service.count_events_by_country(filters=filters)
    return {
        country_code: RecordedEventCountryCount(event_count=event_count)
        for country_code, event_count in counts.items()
    }
