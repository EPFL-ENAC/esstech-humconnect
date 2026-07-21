from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Text, cast, or_
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession

from api.db import get_engine
from api.models.recorded_event import RecordedEvent
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

    async def record_event_from_tool(
        self,
        *,
        event_input: "RecordEventToolInput",
        chat_id: UUID,
        user_id: UUID,
        source_message_id: UUID,
    ) -> RecordedEvent:
        resolved_event_datetime = event_input.event_date.resolve_event_datetime(
            self._now_factory()
        )
        event_datetime = (
            resolved_event_datetime.astimezone(UTC)
            if resolved_event_datetime is not None
            else None
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
        if date_start is not None:
            query = query.where(event_datetime_col >= date_start)
        if date_end is not None:
            query = query.where(event_datetime_col <= date_end)

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
