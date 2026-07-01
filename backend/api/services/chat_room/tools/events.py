import json
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from api.services.chat_room.tools.base import (
    HumConnectTool,
    ToolExecutionContext,
    pydantic_response_function_tool,
)
from api.services.recorded_events import RecordedEventService
from api.utils.relative_dates import (
    iso_date_to_utc_datetime,
    parse_iso_datetime,
)
from api.utils.relative_dates import (
    resolve_relative_datetime as resolve_relative_datetime_from_units,
)

EventDateKind = Literal["absolute", "relative", "unknown"]
EventDateGranularity = Literal[
    "minute", "hour", "day", "week", "month", "year", "unknown"
]
EventDatePrecision = Literal["exact", "fuzzy", "unknown"]
EventRelativeDirection = Literal["past", "future"]
EventLocationPrecision = Literal["exact", "city", "region", "country", "unknown"]
TagMatchMode = Literal["all", "any"]

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RecordEventBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RecordEventRelativeDateInput(RecordEventBaseModel):
    direction: EventRelativeDirection = Field(
        description=(
            "Use past for phrases like 'ago' or 'before'; use future for phrases "
            "like 'in 2 days'."
        )
    )
    years: int | None = Field(default=None, ge=0)
    months: int | None = Field(default=None, ge=0)
    weeks: int | None = Field(default=None, ge=0)
    days: int | None = Field(default=None, ge=0)
    hours: int | None = Field(default=None, ge=0)
    minutes: int | None = Field(default=None, ge=0)
    precision: Literal["exact", "fuzzy"]

    @model_validator(mode="after")
    def require_at_least_one_unit(self) -> Self:
        if not any(
            [
                self.years,
                self.months,
                self.weeks,
                self.days,
                self.hours,
                self.minutes,
            ]
        ):
            raise ValueError("relative event dates require at least one non-zero unit")
        return self

    def resolve_relative_to_datetime(self, reference: datetime) -> datetime:
        return resolve_relative_datetime_from_units(
            reference,
            direction=self.direction,
            years=self.years or 0,
            months=self.months or 0,
            weeks=self.weeks or 0,
            days=self.days or 0,
            hours=self.hours or 0,
            minutes=self.minutes or 0,
        )


class RecordEventDateInput(RecordEventBaseModel):
    kind: EventDateKind
    granularity: EventDateGranularity
    precision: EventDatePrecision
    value: str | None = Field(
        default=None,
        description=(
            "For absolute dates, an ISO date (YYYY-MM-DD) when granularity is "
            "day/week/month/year, or an ISO 8601 datetime when granularity is "
            "hour/minute. Use null for relative or unknown dates."
        ),
    )
    relative: RecordEventRelativeDateInput | None = Field(
        default=None,
        description=(
            "Required only when kind is relative. For '2 days ago', use direction "
            "'past', days 2, precision 'exact'. For 'in a few weeks', use "
            "direction 'future', weeks 3, precision 'fuzzy'."
        ),
    )

    @model_validator(mode="after")
    def validate_shape_for_kind(self) -> Self:
        if self.kind == "absolute":
            if self.relative is not None:
                raise ValueError("absolute event dates cannot include relative offsets")
            if self.value is None:
                raise ValueError("absolute event dates require a value")
            if self.granularity in {"minute", "hour"}:
                parse_iso_datetime(self.value)
            else:
                iso_date_to_utc_datetime(self.value)
        elif self.kind == "relative":
            if self.relative is None:
                raise ValueError("relative event dates require relative offsets")
            if self.value is not None:
                raise ValueError("relative event dates cannot include absolute values")
            if self.precision != self.relative.precision:
                raise ValueError(
                    "relative event date precision must match relative precision"
                )
        else:
            if self.value is not None or self.relative is not None:
                raise ValueError("unknown event dates cannot include date values")
            if self.granularity != "unknown" or self.precision != "unknown":
                raise ValueError(
                    "unknown event dates require unknown granularity and precision"
                )
        return self

    def resolve_event_datetime(self, reference: datetime) -> str | None:
        if self.kind == "unknown":
            return None
        if self.kind == "absolute":
            if self.value is None:
                return None
            if self.granularity in {"minute", "hour"}:
                return parse_iso_datetime(self.value).isoformat()
            return iso_date_to_utc_datetime(self.value).isoformat()
        if self.relative is None:
            return None
        return self.relative.resolve_relative_to_datetime(reference).isoformat()


class RecordEventLocationInput(RecordEventBaseModel):
    value: NonEmptyString | None = Field(
        description="The event location, or null if absent."
    )
    precision: EventLocationPrecision

    @model_validator(mode="after")
    def validate_unknown_location(self) -> Self:
        if self.value is None and self.precision != "unknown":
            raise ValueError("missing event locations require unknown precision")
        return self


class RecordEventToolInput(RecordEventBaseModel):
    original_text: NonEmptyString = Field(
        description="The exact user text that contains the event."
    )
    event_name: NonEmptyString = Field(description="A short human-readable event name.")
    event_date: RecordEventDateInput
    event_location: RecordEventLocationInput
    tags: list[NonEmptyString]

    @model_validator(mode="before")
    @classmethod
    def decode_json_string_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        decoded = dict(data)
        for field_name in ["event_date", "event_location", "tags"]:
            field_value = decoded.get(field_name)
            if isinstance(field_value, str):
                try:
                    decoded[field_name] = json.loads(field_value)
                except json.JSONDecodeError:
                    pass
        return decoded


class RecallEventsToolInput(RecordEventBaseModel):
    keyword: NonEmptyString | None = Field(
        default=None,
        description=(
            "Optional keyword or phrase to find in event names, original text, "
            "locations, or tags."
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
    tags: list[NonEmptyString] = Field(
        default_factory=list,
        description="Optional tags to match against recorded event tags.",
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
    "Use relative dates for phrases like '3 days ago' so the backend can "
    "resolve them against the current datetime. For fuzzy phrases like "
    "'a few weeks ago', use the numeric value 3 and precision 'fuzzy'."
)


RECALL_EVENTS_TOOL_DESCRIPTION = (
    "Recall previously recorded events across all chats by keyword, event "
    "datetime range, and tags. Use this before answering questions that ask "
    "about prior events, timelines, repeated symptoms, or links between events."
)


async def execute_record_event_tool(
    arguments: dict[str, object],
    context: ToolExecutionContext | None = None,
) -> str:
    try:
        event_input = RecordEventToolInput.model_validate(arguments)
    except ValidationError as e:
        raise ValueError(f"record_event received invalid event data: {e}") from e

    if context is None:
        raise ValueError("record_event requires chat execution context.")

    event = await RecordedEventService().record_event_from_tool(
        event_input=event_input,
        chat_id=context.chat_id,
        user_id=context.user_id,
        source_message_id=context.source_message_id,
    )
    return event.to_tool_response()


async def execute_recall_events_tool(
    arguments: dict[str, object],
    context: ToolExecutionContext | None = None,
) -> str:
    try:
        recall_input = RecallEventsToolInput.model_validate(arguments)
    except ValidationError as e:
        raise ValueError(f"recall_events received invalid query data: {e}") from e

    if context is None:
        raise ValueError("recall_events requires chat execution context.")

    events = await RecordedEventService().recall_events_from_tool(
        recall_input=recall_input,
        user_id=context.user_id,
    )
    return json.dumps(
        {
            "message": f"Recalled {len(events)} event(s).",
            "events": [event.model_dump(mode="json") for event in events],
        },
        indent=2,
    )


RECORD_EVENT_TOOL = HumConnectTool(
    name="record_event",
    label="Record event",
    definition=pydantic_response_function_tool(
        RecordEventToolInput,
        name="record_event",
        description=RECORD_EVENT_TOOL_DESCRIPTION,
    ),
    execute=execute_record_event_tool,
)

RECALL_EVENTS_TOOL = HumConnectTool(
    name="recall_events",
    label="Recall events",
    definition=pydantic_response_function_tool(
        RecallEventsToolInput,
        name="recall_events",
        description=RECALL_EVENTS_TOOL_DESCRIPTION,
    ),
    execute=execute_recall_events_tool,
)
