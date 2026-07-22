import json
from calendar import monthrange
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from api.models.recorded_event import EventLocation, EventTag, RecordedEventResponse
from api.models.user_profile import ProfessionCategory
from api.services.chat_room.tools.base import (
    HumConnectTool,
    ToolExecutionContext,
)
from api.services.recorded_events import RecordedEventService
from api.utils.datetime_utils import parse_iso_datetime
from api.utils.pydantic_types import NonEmptyString
from api.utils.relative_dates import add_calendar_months

EventDateGranularity = Literal[
    "minute", "hour", "day", "week", "month", "year", "unknown"
]
EventDatePrecision = Literal["exact", "fuzzy", "unknown"]
EventDateBoundary = Literal["start", "end"]
TagMatchMode = Literal["all", "any"]


class RecordEventBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RecordEventTemporalEntryInput(RecordEventBaseModel):
    kind: Literal["absolute", "relative"]
    value: int = Field(
        description=(
            "The calendar or clock value when kind is absolute, or a signed "
            "offset when kind is relative. Negative offsets refer to the past."
        )
    )


class RecordEventRelativeTemporalEntryInput(RecordEventBaseModel):
    kind: Literal["relative"]
    value: int = Field(
        description=(
            "A signed offset. Negative values refer to the past and positive "
            "values refer to the future."
        )
    )


class RecordEventDaySelectionInput(RecordEventBaseModel):
    mode: Literal["day"]
    day: RecordEventTemporalEntryInput = Field(
        description=(
            "An absolute day of the month or a relative day offset. For example, "
            "absolute 5 means the fifth day of the resolved month, while relative "
            "-1 means yesterday."
        )
    )


class RecordEventWeekSelectionInput(RecordEventBaseModel):
    mode: Literal["week"]
    week: RecordEventRelativeTemporalEntryInput = Field(
        description=(
            "The relative ISO week. Use -1 for last week, 0 for this week, and 1 "
            "for next week."
        )
    )
    weekday: int | None = Field(
        ge=1,
        le=7,
        description=(
            "An optional ISO weekday within the selected week. Monday is 1 and "
            "Sunday is 7. Use null for the whole week."
        ),
    )


RecordEventDayOrWeekInput = Annotated[
    RecordEventDaySelectionInput | RecordEventWeekSelectionInput,
    Field(discriminator="mode"),
]


class RecordEventDateInput(RecordEventBaseModel):
    year: RecordEventTemporalEntryInput | None
    month: RecordEventTemporalEntryInput | None
    day_selection: RecordEventDayOrWeekInput | None = Field(
        description=(
            "Select either a single absolute or relative day, or a relative week "
            "with an optional weekday. Use null when neither is known."
        )
    )
    hour: RecordEventTemporalEntryInput | None
    minute: RecordEventTemporalEntryInput | None
    precision: EventDatePrecision
    timezone: str | None = Field(
        description=(
            "An IANA timezone such as Europe/Zurich when it can be inferred "
            "unambiguously from the event; otherwise null to use UTC."
        )
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_components(self) -> Self:
        component_names = ("year", "month", "hour", "minute")
        components = {
            name: getattr(self, name)
            for name in component_names
            if getattr(self, name) is not None
        }
        if not components and self.day_selection is None:
            if self.precision != "unknown" or self.timezone is not None:
                raise ValueError(
                    "unknown event dates require unknown precision and no timezone"
                )
            return self
        if self.precision == "unknown":
            raise ValueError("known event dates require exact or fuzzy precision")

        absolute_bounds = {
            "year": (1, 9999),
            "month": (1, 12),
            "hour": (0, 23),
            "minute": (0, 59),
        }
        for name, component in components.items():
            if component.kind != "absolute":
                continue
            lower, upper = absolute_bounds[name]
            if not lower <= component.value <= upper:
                raise ValueError(f"absolute {name} must be between {lower} and {upper}")

        if isinstance(self.day_selection, RecordEventDaySelectionInput):
            day = self.day_selection.day
            if day.kind == "absolute" and not 1 <= day.value <= 31:
                raise ValueError("absolute day must be between 1 and 31")
        return self

    @property
    def granularity(self) -> EventDateGranularity:
        if self.minute is not None:
            return "minute"
        if self.hour is not None:
            return "hour"
        if isinstance(self.day_selection, RecordEventDaySelectionInput):
            return "day"
        if isinstance(self.day_selection, RecordEventWeekSelectionInput):
            return "day" if self.day_selection.weekday is not None else "week"
        if self.month is not None:
            return "month"
        if self.year is not None:
            return "year"
        return "unknown"

    @staticmethod
    def _replace_year_or_month(
        value: datetime,
        *,
        year: int | None = None,
        month: int | None = None,
    ) -> datetime:
        target_year = year if year is not None else value.year
        target_month = month if month is not None else value.month
        target_day = min(value.day, monthrange(target_year, target_month)[1])
        return value.replace(year=target_year, month=target_month, day=target_day)

    @staticmethod
    def _is_valid_local_datetime(value: datetime, zone: ZoneInfo) -> bool:
        round_trip = value.astimezone(UTC).astimezone(zone)
        return round_trip.replace(fold=value.fold) == value

    def _normalize_calendar_only(
        self,
        value: datetime,
        *,
        boundary: EventDateBoundary,
    ) -> datetime:
        granularity = self.granularity
        if granularity == "year":
            if boundary == "start":
                return value.replace(month=1, day=1, hour=0, minute=0)
            return value.replace(
                month=12,
                day=31,
                hour=23,
                minute=59,
                second=59,
                microsecond=999999,
            )
        if granularity == "month":
            if boundary == "start":
                return value.replace(day=1, hour=0, minute=0)
            return value.replace(
                day=monthrange(value.year, value.month)[1],
                hour=23,
                minute=59,
                second=59,
                microsecond=999999,
            )
        if granularity == "week":
            week_start = value - timedelta(days=value.weekday())
            if boundary == "start":
                return week_start.replace(hour=0, minute=0)
            return (week_start + timedelta(days=6)).replace(
                hour=23,
                minute=59,
                second=59,
                microsecond=999999,
            )
        if boundary == "start":
            return value.replace(hour=0, minute=0)
        return value.replace(
            hour=23,
            minute=59,
            second=59,
            microsecond=999999,
        )

    def resolve_event_datetime(
        self,
        reference: datetime,
        *,
        boundary: EventDateBoundary = "start",
    ) -> datetime | None:
        if self.granularity == "unknown":
            return None

        zone = ZoneInfo(self.timezone or "UTC")
        resolved = reference.astimezone(zone).replace(second=0, microsecond=0, fold=0)

        if self.year is not None:
            if self.year.kind == "relative":
                resolved = add_calendar_months(resolved, self.year.value * 12)
            else:
                resolved = self._replace_year_or_month(resolved, year=self.year.value)

        if self.month is not None:
            if self.month.kind == "relative":
                resolved = add_calendar_months(resolved, self.month.value)
            else:
                resolved = self._replace_year_or_month(resolved, month=self.month.value)

        if isinstance(self.day_selection, RecordEventDaySelectionInput):
            day = self.day_selection.day
            if day.kind == "relative":
                resolved += timedelta(days=day.value)
            else:
                try:
                    resolved = resolved.replace(day=day.value)
                except ValueError as exc:
                    raise ValueError(
                        "absolute day is invalid for the resolved month"
                    ) from exc
        elif isinstance(self.day_selection, RecordEventWeekSelectionInput):
            resolved += timedelta(weeks=self.day_selection.week.value)
            if self.day_selection.weekday is not None:
                resolved += timedelta(
                    days=self.day_selection.weekday - resolved.isoweekday()
                )

        if self.hour is not None:
            if self.hour.kind == "relative":
                resolved = (
                    resolved.astimezone(UTC) + timedelta(hours=self.hour.value)
                ).astimezone(zone)
            else:
                resolved = resolved.replace(
                    hour=self.hour.value,
                    minute=0 if self.minute is None else resolved.minute,
                    fold=0,
                )

        if self.minute is not None:
            if self.minute.kind == "relative":
                resolved = (
                    resolved.astimezone(UTC) + timedelta(minutes=self.minute.value)
                ).astimezone(zone)
            else:
                resolved = resolved.replace(minute=self.minute.value, fold=0)

        if self.hour is None and self.minute is None:
            resolved = self._normalize_calendar_only(resolved, boundary=boundary)
        else:
            resolved = resolved.replace(second=0, microsecond=0)

        if not self._is_valid_local_datetime(resolved, zone):
            raise ValueError("event date resolves to a nonexistent local time")
        return resolved


class RecordEventSeverityInput(RecordEventBaseModel):
    local: float = Field(
        ge=0,
        le=10,
        description=(
            "Severity for the directly affected person, facility, community, or "
            "local area, from 0 (no meaningful impact) to 10 (catastrophic impact)."
        ),
    )
    country: float = Field(
        ge=0,
        le=10,
        description=(
            "Severity for the affected country as a whole, from 0 (no meaningful "
            "national impact) to 10 (catastrophic national impact)."
        ),
    )
    global_: float = Field(
        alias="global",
        ge=0,
        le=10,
        description=(
            "Severity at the international or global scale, from 0 (no meaningful "
            "global impact) to 10 (catastrophic global impact). Assess this "
            "independently from local and country severity."
        ),
    )


class RecordEventLocationInput(EventLocation):
    pass


class RecordEventToolInput(RecordEventBaseModel):
    original_text: NonEmptyString = Field(
        description="The exact user text that contains the event."
    )
    event_name: NonEmptyString = Field(description="A short human-readable event name.")
    event_date: RecordEventDateInput
    event_end_date: RecordEventDateInput | None = Field(
        description=(
            "The inclusive end date for an event interval, using the same component "
            "format as event_date, or null for a point event. Never provide an end "
            "date without at least a fuzzy known event_date."
        )
    )
    event_location: RecordEventLocationInput
    tags: list[EventTag] = Field(
        min_length=1,
        description=(
            "One or more fixed event categories. Select every applicable category. "
            "Use health_incident for individual symptoms, injuries, or diagnoses and "
            "disease_outbreak for suspected or confirmed population-level spread. "
            "Use supply_shortage for missing consumables or medicines and "
            "equipment_issue for unavailable or broken equipment. Use other only "
            "when no specific category applies."
        ),
    )
    keywords: list[NonEmptyString] = Field(
        description=(
            "Free-form search terms copied or inferred from the event. Use an empty "
            "list when no useful keywords are available."
        )
    )
    affected_profession_categories: list[ProfessionCategory] = Field(
        description=(
            "Profession categories whose work, services, or beneficiaries are "
            "affected by the event. Use an empty list when this cannot be inferred."
        )
    )
    response_profession_categories: list[ProfessionCategory] = Field(
        description=(
            "Profession categories positioned to mitigate or resolve the event. "
            "Use an empty list when this cannot be inferred."
        )
    )
    severity: RecordEventSeverityInput = Field(
        description=(
            "Required severity assessment at local, country, and global scales. "
            "Rate each scale independently using the currently known impact; a "
            "serious new disease case can be severe locally and nationally while "
            "remaining low globally."
        )
    )

    @model_validator(mode="before")
    @classmethod
    def decode_json_string_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        decoded = dict(data)
        for field_name in [
            "event_date",
            "event_end_date",
            "event_location",
            "tags",
            "keywords",
            "affected_profession_categories",
            "response_profession_categories",
            "severity",
        ]:
            field_value = decoded.get(field_name)
            if isinstance(field_value, str):
                try:
                    decoded[field_name] = json.loads(field_value)
                except json.JSONDecodeError:
                    pass
        return decoded

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        if self.event_end_date is not None:
            if self.event_date.granularity == "unknown":
                raise ValueError("event end dates require a known event start date")
            if self.event_end_date.granularity == "unknown":
                raise ValueError("event end dates must contain a known date")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("event tags must be unique")
        if "other" in self.tags and len(self.tags) != 1:
            raise ValueError("other cannot be combined with specific event tags")
        return self


class RecallEventsToolInput(RecordEventBaseModel):
    keyword: NonEmptyString | None = Field(
        default=None,
        description=(
            "Optional keyword or phrase to find in event names, original text, "
            "locations, or free-form keywords."
        ),
    )
    date_start: str | None = Field(
        default=None,
        description=(
            "Optional inclusive ISO 8601 lower bound for interval overlap. Events "
            "whose effective end is before this value are excluded. Use null if no "
            "lower bound is needed."
        ),
    )
    date_end: str | None = Field(
        default=None,
        description=(
            "Optional inclusive ISO 8601 upper bound for interval overlap. Events "
            "whose effective start is after this value are excluded. Use null if no "
            "upper bound is needed."
        ),
    )
    tags: list[EventTag] = Field(
        default_factory=list,
        description="Optional fixed event tags to match exactly.",
    )
    tag_match: TagMatchMode = Field(
        default="all",
        description="Use all to require every tag, or any to match at least one tag.",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of matching events to return.",
    )

    @model_validator(mode="before")
    @classmethod
    def decode_json_string_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        decoded = dict(data)
        tags = decoded.get("tags")
        if isinstance(tags, str):
            try:
                decoded["tags"] = json.loads(tags)
            except json.JSONDecodeError:
                pass
        return decoded

    @model_validator(mode="after")
    def validate_date_bounds(self) -> Self:
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("event tags must be unique")
        date_start = self.parsed_date_start()
        date_end = self.parsed_date_end()
        if date_start is not None and date_end is not None and date_start > date_end:
            raise ValueError("date_start must be before or equal to date_end")
        return self

    def parsed_date_start(self) -> datetime | None:
        if self.date_start is None:
            return None
        return parse_iso_datetime(self.date_start)

    def parsed_date_end(self) -> datetime | None:
        if self.date_end is None:
            return None
        return parse_iso_datetime(self.date_end)


RECORD_EVENT_TOOL_DESCRIPTION = (
    "Record a user-provided fact or event in persistent storage. "
    "Classify it with all applicable fixed tags, keep free-form search terms in "
    "keywords, and identify affected and responding profession categories when "
    "they can be inferred. Structure the location into administrative, place, and "
    "address fields while preserving the exact location phrase in raw_text. Only "
    "include coordinates when the user explicitly provides them; never estimate "
    "coordinates. Independently assess severity from 0 to 10 at local, "
    "country, and global scales based on the currently known impact. "
    "Express dates with absolute calendar or clock values and signed relative "
    "offsets for each supplied component. Use day_selection mode day for an "
    "absolute day of the month or a relative day offset, and mode week for a "
    "relative ISO week with an optional ISO weekday (Monday 1 through Sunday 7). "
    "For 'yesterday at 8pm', use mode day with relative day -1 and absolute hour "
    "20. For 'the 5th of last month', use relative month -1 and mode day with "
    "absolute day 5. For 'Thursday of last week', use mode week with relative "
    "week -1 and weekday 4. Ask for clarification when a named weekday has no "
    "explicit week context. For 'in 2 hours', use relative hour 2. For 'a few "
    "weeks ago', use mode week with relative week -3, null weekday, and fuzzy "
    "precision. Supply an "
    "IANA timezone such as Europe/Zurich when the event location makes it "
    "unambiguous; otherwise use null and the backend will resolve in UTC. Use "
    "event_end_date for intervals: for 'a flood between the 4th of June and "
    "yesterday', put June 4 in event_date and mode day with relative day -1 in "
    "event_end_date. "
    "Use null for event_end_date when the event is a point in time. If only an end "
    "is known, ask the user for at least a fuzzy start before recording the event."
)


RECALL_EVENTS_TOOL_DESCRIPTION = (
    "Recall previously recorded events across all chats by keyword, event "
    "datetime overlap range, and exact fixed tags. Point events and event intervals "
    "are both matched inclusively. Use this before answering questions "
    "that ask about prior events, timelines, repeated symptoms, or links between "
    "events."
)


async def _record_event(
    event_input: RecordEventToolInput,
    tool_context: ToolExecutionContext,
) -> str:
    event = await RecordedEventService().record_event_from_tool(
        event_input=event_input,
        chat_id=tool_context.chat_id,
        user_id=tool_context.user_id,
        source_message_id=tool_context.source_message_id,
    )
    return event.to_tool_response()


async def _recall_events(
    recall_input: RecallEventsToolInput,
    tool_context: ToolExecutionContext,
) -> str:
    events = await RecordedEventService().recall_events_from_tool(
        recall_input=recall_input,
        user_id=tool_context.user_id,
    )
    return json.dumps(
        {
            "message": f"Recalled {len(events)} event(s).",
            "events": [
                RecordedEventResponse.from_recorded_event(event).model_dump(mode="json")
                for event in events
            ],
        },
        indent=2,
    )


RECORD_EVENT_TOOL = HumConnectTool.from_async_with_context_handler(
    name="record_event",
    label="Record event",
    input_model=RecordEventToolInput,
    description=RECORD_EVENT_TOOL_DESCRIPTION,
    invalid_input_message="record_event received invalid event data",
    handler=_record_event,
)

RECALL_EVENTS_TOOL = HumConnectTool.from_async_with_context_handler(
    name="recall_events",
    label="Recall events",
    input_model=RecallEventsToolInput,
    description=RECALL_EVENTS_TOOL_DESCRIPTION,
    invalid_input_message="recall_events received invalid query data",
    handler=_recall_events,
)
