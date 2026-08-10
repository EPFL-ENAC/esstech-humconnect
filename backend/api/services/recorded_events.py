from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Text, cast, func, or_
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession

from api.db import get_engine
from api.models.recorded_event import (
    UNKNOWN_COUNTRY_CODE,
    ListRecordedEventsFilters,
    RecordedEvent,
    RecordedEventListSort,
)
from api.utils.datetime_utils import utc_now

if TYPE_CHECKING:
    from api.services.chat_room.tools.events import (
        RecallEventsToolInput,
        RecordEventToolInput,
    )


class RecordedEventService:
    def __init__(
        self,
        *,
        session_factory: type[AsyncSQLModelSession] = AsyncSQLModelSession,
        engine_factory: Callable[[], AsyncEngine] = get_engine,
        now_factory: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._engine_factory = engine_factory
        self._now_factory = now_factory

    async def list_events(
        self,
        *,
        filters: ListRecordedEventsFilters,
        sort: RecordedEventListSort,
        page: int,
        page_size: int,
    ) -> tuple[list[RecordedEvent], int]:
        filter_clauses = _filter_clauses(filters)
        count_query = select(func.count(col(RecordedEvent.id))).where(*filter_clauses)
        events_query = (
            select(RecordedEvent)
            .where(*filter_clauses)
            .order_by(*_sort_clauses(sort))
            .limit(page_size)
            .offset((page - 1) * page_size)
        )

        async with self._session_factory(
            self._engine_factory(),
            expire_on_commit=False,
        ) as session:
            total_count = (await session.exec(count_query)).one()
            events = (await session.exec(events_query)).all()
            return list(events), total_count

    async def count_events_by_country(
        self,
        *,
        filters: ListRecordedEventsFilters,
    ) -> dict[str, int]:
        country_key = func.coalesce(
            col(RecordedEvent.location_country_code),
            UNKNOWN_COUNTRY_CODE,
        ).label("country_code")
        event_count = func.count(col(RecordedEvent.id)).label("event_count")
        query = (
            select(country_key, event_count)
            .where(*_filter_clauses(filters))
            .group_by(country_key)
        )

        async with self._session_factory(
            self._engine_factory(),
            expire_on_commit=False,
        ) as session:
            result = await session.exec(query)
            return {country_code: count for country_code, count in result.all()}

    async def record_event_from_tool(
        self,
        *,
        event_input: "RecordEventToolInput",
        chat_id: UUID,
        user_id: UUID,
        source_message_id: UUID,
    ) -> RecordedEvent:
        reference_datetime = self._now_factory()
        resolved_event_datetime = event_input.event_date.resolve_event_datetime(
            reference_datetime,
        )
        resolved_event_end_datetime = (
            event_input.event_end_date.resolve_event_datetime(
                reference_datetime,
                boundary="end",
            )
            if event_input.event_end_date is not None
            else None
        )
        event_datetime = (
            resolved_event_datetime.astimezone(UTC)
            if resolved_event_datetime is not None
            else None
        )
        event_end_datetime = (
            resolved_event_end_datetime.astimezone(UTC)
            if resolved_event_end_datetime is not None
            else None
        )
        if (
            event_datetime is not None
            and event_end_datetime is not None
            and event_end_datetime < event_datetime
        ):
            raise ValueError(
                "event end date must be after or equal to event start date"
            )

        recorded_event = RecordedEvent(
            chat_id=chat_id,
            initiated_by_user_id=user_id,
            source_message_id=source_message_id,
            original_text=event_input.original_text,
            event_name=event_input.event_name,
            event_datetime=event_datetime,
            event_date_granularity=event_input.event_date.granularity,
            event_date_precision=event_input.event_date.precision,
            event_date_input=event_input.event_date.model_dump(mode="json"),
            event_end_datetime=event_end_datetime,
            event_end_date_granularity=(
                event_input.event_end_date.granularity
                if event_input.event_end_date is not None
                else None
            ),
            event_end_date_precision=(
                event_input.event_end_date.precision
                if event_input.event_end_date is not None
                else None
            ),
            event_end_date_input=(
                event_input.event_end_date.model_dump(mode="json")
                if event_input.event_end_date is not None
                else None
            ),
            location_raw_text=event_input.event_location.raw_text,
            location_continent=event_input.event_location.continent,
            location_country_code=event_input.event_location.country_code,
            location_region=event_input.event_location.region,
            location_city=event_input.event_location.city,
            location_address=event_input.event_location.address,
            location_place_name=event_input.event_location.place_name,
            location_detail=event_input.event_location.detail,
            location_latitude=(
                event_input.event_location.coordinates.latitude
                if event_input.event_location.coordinates is not None
                else None
            ),
            location_longitude=(
                event_input.event_location.coordinates.longitude
                if event_input.event_location.coordinates is not None
                else None
            ),
            tags=list(event_input.tags),
            keywords=list(event_input.keywords),
            affected_profession_categories=list(
                event_input.affected_profession_categories
            ),
            response_profession_categories=list(
                event_input.response_profession_categories
            ),
            local_severity=event_input.severity.local,
            country_severity=event_input.severity.country,
            global_severity=event_input.severity.global_,
        )

        async with self._session_factory(
            self._engine_factory(),
            expire_on_commit=False,
        ) as session:
            session.add(recorded_event)
            await session.commit()
            await session.refresh(recorded_event)

        return recorded_event

    async def recall_events_from_tool(
        self,
        *,
        recall_input: "RecallEventsToolInput",
        user_id: UUID,
    ) -> list[RecordedEvent]:
        query = (
            select(RecordedEvent)
            .where(RecordedEvent.initiated_by_user_id == user_id)
            .order_by(col(RecordedEvent.created_at).desc())
            .limit(recall_input.limit)
        )

        date_start = recall_input.parsed_date_start()
        date_end = recall_input.parsed_date_end()
        event_datetime_col = col(RecordedEvent.event_datetime)
        event_end_datetime_col = col(RecordedEvent.event_end_datetime)
        effective_start = func.coalesce(event_datetime_col, event_end_datetime_col)
        effective_end = func.coalesce(event_end_datetime_col, event_datetime_col)
        if date_start is not None:
            query = query.where(effective_end >= date_start)
        if date_end is not None:
            query = query.where(effective_start <= date_end)

        if recall_input.keyword is not None:
            keyword_pattern = f"%{recall_input.keyword}%"
            query = query.where(
                or_(
                    col(RecordedEvent.event_name).ilike(keyword_pattern),
                    col(RecordedEvent.original_text).ilike(keyword_pattern),
                    col(RecordedEvent.location_raw_text).ilike(keyword_pattern),
                    col(RecordedEvent.location_continent).ilike(keyword_pattern),
                    col(RecordedEvent.location_country_code).ilike(keyword_pattern),
                    col(RecordedEvent.location_region).ilike(keyword_pattern),
                    col(RecordedEvent.location_city).ilike(keyword_pattern),
                    col(RecordedEvent.location_address).ilike(keyword_pattern),
                    col(RecordedEvent.location_place_name).ilike(keyword_pattern),
                    col(RecordedEvent.location_detail).ilike(keyword_pattern),
                    cast(RecordedEvent.keywords, Text).ilike(keyword_pattern),
                )
            )

        if recall_input.tags:
            tags_jsonb = col(RecordedEvent.tags)
            tag_filters = [tags_jsonb.contains([tag]) for tag in recall_input.tags]
            if recall_input.tag_match == "all":
                for tag_filter in tag_filters:
                    query = query.where(tag_filter)
            else:
                query = query.where(or_(*tag_filters))

        async with self._session_factory(
            self._engine_factory(),
            expire_on_commit=False,
        ) as session:
            result = await session.exec(query)
            return list(result.all())


def _filter_clauses(
    filters: ListRecordedEventsFilters,
) -> tuple[ColumnElement[bool], ...]:
    clauses: list[ColumnElement[bool]] = []

    if filters.keyword is not None:
        clauses.append(cast(RecordedEvent.keywords, Text).ilike(f"%{filters.keyword}%"))

    if filters.tags:
        tags_jsonb = col(RecordedEvent.tags)
        clauses.append(or_(*(tags_jsonb.contains([tag]) for tag in filters.tags)))

    if filters.affected_profession_categories:
        affected_jsonb = col(RecordedEvent.affected_profession_categories)
        clauses.append(
            or_(
                *(
                    affected_jsonb.contains([category])
                    for category in filters.affected_profession_categories
                )
            )
        )

    if filters.response_profession_categories:
        response_jsonb = col(RecordedEvent.response_profession_categories)
        clauses.append(
            or_(
                *(
                    response_jsonb.contains([category])
                    for category in filters.response_profession_categories
                )
            )
        )

    return tuple(clauses)


def _sort_clauses(
    sort: RecordedEventListSort,
) -> tuple[ColumnElement[Any], ...]:
    event_datetime = col(RecordedEvent.event_datetime)
    created_at = col(RecordedEvent.created_at)
    event_id = col(RecordedEvent.id)

    if sort == "event_date_asc":
        return (
            event_datetime.asc().nulls_last(),
            created_at.asc(),
            event_id.asc(),
        )
    if sort == "event_date_desc":
        return (
            event_datetime.desc().nulls_last(),
            created_at.desc(),
            event_id.desc(),
        )
    if sort == "added_date_asc":
        return created_at.asc(), event_id.asc()
    return created_at.desc(), event_id.desc()
