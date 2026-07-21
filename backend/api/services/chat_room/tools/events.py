import json
from calendar import monthrange
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Self
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


class RecordEventDateInput(RecordEventBaseModel):
    year: RecordEventTemporalEntryInput | None
    month: RecordEventTemporalEntryInput | None
    week: RecordEventRelativeTemporalEntryInput | None
    day: RecordEventTemporalEntryInput | None
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
        component_names = ("year", "month", "week", "day", "hour", "minute")
        components = {
            name: getattr(self, name)
            for name in component_names
            if getattr(self, name) is not None
        }
        if not components:
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
            "day": (1, 31),
            "hour": (0, 23),
            "minute": (0, 59),
        }
        for name, component in components.items():
            if component.kind != "absolute":
                continue
            lower, upper = absolute_bounds[name]
            if not lower <= component.value <= upper:
                raise ValueError(f"absolute {name} must be between {lower} and {upper}")
        return self

    @property
    def granularity(self) -> EventDateGranularity:
        for name in ("minute", "hour", "day", "week", "month", "year"):
            if getattr(self, name) is not None:
                return name
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

    def _normalize_calendar_only(self, value: datetime) -> datetime:
        granularity = self.granularity
        if granularity == "year":
            return value.replace(month=1, day=1, hour=0, minute=0)
        if granularity == "month":
            return value.replace(day=1, hour=0, minute=0)
        if granularity == "week":
            return (value - timedelta(days=value.weekday())).replace(hour=0, minute=0)
        return value.replace(hour=0, minute=0)

    def resolve_event_datetime(self, reference: datetime) -> datetime | None:
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

        if self.week is not None:
            resolved += timedelta(weeks=self.week.value)

        if self.day is not None:
            if self.day.kind == "relative":
                resolved += timedelta(days=self.day.value)
            else:
                try:
                    resolved = resolved.replace(day=self.day.value)
                except ValueError as exc:
                    raise ValueError(
                        "absolute day is invalid for the resolved month"
                    ) from exc

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
            resolved = self._normalize_calendar_only(resolved)

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
    def validate_tags(self) -> Self:
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
            "Optional inclusive ISO 8601 datetime lower bound for event_datetime. "
            "Use null if no lower bound is needed."
        ),
    )
    date_end: str | None = Field(
        default=None,
        description=(
            "Optional inclusive ISO 8601 datetime upper bound for event_datetime. "
            "Use null if no upper bound is needed."
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
    "offsets for each supplied component. For 'yesterday at 8pm', use relative "
    "day -1 and absolute hour 20. For 'the 5th of last month', use relative "
    "month -1 and absolute day 5. For 'in 2 hours', use relative hour 2. For "
    "'a few weeks ago', use relative week -3 and fuzzy precision. Supply an "
    "IANA timezone such as Europe/Zurich when the event location makes it "
    "unambiguous; otherwise use null and the backend will resolve in UTC."
)


RECALL_EVENTS_TOOL_DESCRIPTION = (
    "Recall previously recorded events across all chats by keyword, event "
    "datetime range, and exact fixed tags. Use this before answering questions "
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
