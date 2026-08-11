import json
from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias
from uuid import UUID, uuid4

import pycountry
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Index,
    String,
    Text,
    cast,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from api.models.user_profile import ProfessionCategory
from api.utils.datetime_utils import utc_now
from api.utils.pydantic_types import NonEmptyString

EventTag = Literal[
    "health_incident",
    "disease_outbreak",
    "mortality_or_safe_burial",
    "supply_shortage",
    "equipment_issue",
    "staffing_gap",
    "infrastructure_or_energy_failure",
    "wash_issue",
    "service_disruption",
    "access_constraint",
    "security_incident",
    "displacement",
    "food_or_sym_o_nutrition_insecurity",
    "environmental_hazard",
    "coordination_or_information_gap",
    "community_concern",
    "other",
]
EventContinent = Literal[
    "africa",
    "antarctica",
    "asia",
    "europe",
    "north_america",
    "oceania",
    "south_america",
]
CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
UNKNOWN_COUNTRY_CODE = "UNKNOWN"
RecordedEventListSort = Literal[
    "event_date_asc",
    "event_date_desc",
    "added_date_asc",
    "added_date_desc",
]
DEFAULT_RECORDED_EVENT_LIST_SORT: RecordedEventListSort = "event_date_desc"


EVENT_TAGS: tuple[EventTag, ...] = (
    "health_incident",
    "disease_outbreak",
    "mortality_or_safe_burial",
    "supply_shortage",
    "equipment_issue",
    "staffing_gap",
    "infrastructure_or_energy_failure",
    "wash_issue",
    "service_disruption",
    "access_constraint",
    "security_incident",
    "displacement",
    "food_or_sym_o_nutrition_insecurity",
    "environmental_hazard",
    "coordination_or_information_gap",
    "community_concern",
    "other",
)
EVENT_CONTINENTS: tuple[EventContinent, ...] = (
    "africa",
    "antarctica",
    "asia",
    "europe",
    "north_america",
    "oceania",
    "south_america",
)


class EventCoordinates(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class EventLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    raw_text: NonEmptyString | None = Field(
        description=(
            "The exact location phrase from the user's message, or null when no "
            "location phrase is present."
        )
    )
    continent: EventContinent | None = Field(
        description="The continent when it is unambiguous, otherwise null."
    )
    country_code: CountryCode | None = Field(
        description=(
            "The uppercase ISO 3166-1 alpha-2 country code when unambiguous, "
            "otherwise null."
        )
    )
    region: NonEmptyString | None = Field(
        description="The state, province, district, or other subnational region."
    )
    city: NonEmptyString | None = Field(
        description="The city, town, or village, otherwise null."
    )
    address: NonEmptyString | None = Field(
        description="A street or postal address, otherwise null."
    )
    place_name: NonEmptyString | None = Field(
        description=(
            "A named or descriptive feature such as a lake, river, clinic, camp, "
            "or 'the bridge'."
        )
    )
    detail: NonEmptyString | None = Field(
        description=(
            "Additional relative context such as 'the river near the bridge', "
            "otherwise null."
        )
    )
    coordinates: EventCoordinates | None = Field(
        description=(
            "Coordinates explicitly supplied by the user. Never estimate or infer "
            "coordinates from a place name."
        )
    )

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, value: str | None) -> str | None:
        if value is not None and pycountry.countries.get(alpha_2=value) is None:
            raise ValueError("country_code must be an ISO 3166-1 alpha-2 code")
        return value


class RecordedEvent(SQLModel, table=True):
    __tablename__ = "recordedevent"
    __table_args__ = (
        CheckConstraint(
            "(location_latitude IS NULL) = (location_longitude IS NULL)",
            name="ck_recordedevent_location_coordinate_pair",
        ),
        CheckConstraint(
            "event_end_datetime IS NULL OR event_datetime IS NULL "
            "OR event_end_datetime >= event_datetime",
            name="ck_recordedevent_event_date_range",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    chat_id: UUID = Field(foreign_key="chatsession.id", index=True)
    initiated_by_user_id: UUID = Field(foreign_key="userprofile.id", index=True)
    source_message_id: UUID = Field(foreign_key="message.id", index=True)
    original_text: str
    event_name: str
    event_datetime: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    event_date_granularity: str = Field(index=True)
    event_date_precision: str = Field(index=True)
    event_date_input: dict[str, Any] = Field(
        sa_column=Column(JSON, nullable=False),
    )
    event_end_datetime: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    event_end_date_granularity: str | None = Field(default=None, index=True)
    event_end_date_precision: str | None = Field(default=None, index=True)
    event_end_date_input: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    location_raw_text: str | None = Field(default=None)
    location_continent: EventContinent | None = Field(
        default=None,
        sa_column=Column(
            String,
            CheckConstraint(
                "location_continent IN ("
                "'africa', 'antarctica', 'asia', 'europe', "
                "'north_america', 'oceania', 'south_america'"
                ")",
                name="ck_recordedevent_location_continent",
            ),
            nullable=True,
            index=True,
        ),
    )
    location_country_code: str | None = Field(
        default=None,
        sa_column=Column(
            String(2),
            CheckConstraint(
                "location_country_code ~ '^[A-Z]{2}$'",
                name="ck_recordedevent_location_country_code",
            ),
            nullable=True,
            index=True,
        ),
    )
    location_region: str | None = Field(default=None)
    location_city: str | None = Field(default=None)
    location_address: str | None = Field(default=None)
    location_place_name: str | None = Field(default=None)
    location_detail: str | None = Field(default=None)
    location_latitude: float | None = Field(
        default=None,
        sa_column=Column(
            Float,
            CheckConstraint(
                "location_latitude BETWEEN -90 AND 90",
                name="ck_recordedevent_location_latitude_range",
            ),
            nullable=True,
            index=True,
        ),
    )
    location_longitude: float | None = Field(
        default=None,
        sa_column=Column(
            Float,
            CheckConstraint(
                "location_longitude BETWEEN -180 AND 180",
                name="ck_recordedevent_location_longitude_range",
            ),
            nullable=True,
            index=True,
        ),
    )
    tags: list[EventTag] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
    )
    keywords: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
    )
    affected_profession_categories: list[ProfessionCategory] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
    )
    response_profession_categories: list[ProfessionCategory] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
    )
    local_severity: float | None = Field(
        default=None,
        sa_column=Column(
            Float,
            CheckConstraint(
                "local_severity BETWEEN 0 AND 10",
                name="ck_recordedevent_local_severity_range",
            ),
            nullable=True,
        ),
    )
    country_severity: float | None = Field(
        default=None,
        sa_column=Column(
            Float,
            CheckConstraint(
                "country_severity BETWEEN 0 AND 10",
                name="ck_recordedevent_country_severity_range",
            ),
            nullable=True,
        ),
    )
    global_severity: float | None = Field(
        default=None,
        sa_column=Column(
            Float,
            CheckConstraint(
                "global_severity BETWEEN 0 AND 10",
                name="ck_recordedevent_global_severity_range",
            ),
            nullable=True,
        ),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )

    def to_tool_response(self) -> str:
        event_response = RecordedEventResponse.from_recorded_event(self)
        return json.dumps(
            {
                "message": f"Recorded event: {self.event_name}",
                "event": event_response.model_dump(mode="json"),
            },
            indent=2,
        )

    def event_location(self) -> EventLocation:
        coordinates = None
        if self.location_latitude is not None and self.location_longitude is not None:
            coordinates = EventCoordinates(
                latitude=self.location_latitude,
                longitude=self.location_longitude,
            )
        return EventLocation(
            raw_text=self.location_raw_text,
            continent=self.location_continent,
            country_code=self.location_country_code,
            region=self.location_region,
            city=self.location_city,
            address=self.location_address,
            place_name=self.location_place_name,
            detail=self.location_detail,
            coordinates=coordinates,
        )


_recorded_event_table = SQLModel.metadata.tables["recordedevent"]

Index(
    "ix_recordedevent_tags_gin",
    _recorded_event_table.c["tags"],
    postgresql_using="gin",
)
Index(
    "ix_recordedevent_keywords_text_trgm",
    cast(_recorded_event_table.c["keywords"], Text).label("keywords_text"),
    postgresql_using="gin",
    postgresql_ops={"keywords_text": "gin_trgm_ops"},
)
Index(
    "ix_recordedevent_affected_profession_categories_gin",
    _recorded_event_table.c["affected_profession_categories"],
    postgresql_using="gin",
)
Index(
    "ix_recordedevent_response_profession_categories_gin",
    _recorded_event_table.c["response_profession_categories"],
    postgresql_using="gin",
)


class RecordedEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chat_id: UUID
    initiated_by_user_id: UUID
    source_message_id: UUID
    original_text: str
    event_name: str
    event_datetime: datetime | None
    event_date_granularity: str
    event_date_precision: str
    event_date_input: dict[str, Any]
    event_end_datetime: datetime | None
    event_end_date_granularity: str | None
    event_end_date_precision: str | None
    event_end_date_input: dict[str, Any] | None
    event_location: EventLocation
    tags: list[EventTag]
    keywords: list[str]
    affected_profession_categories: list[ProfessionCategory]
    response_profession_categories: list[ProfessionCategory]
    local_severity: float | None
    country_severity: float | None
    global_severity: float | None
    created_at: datetime

    @classmethod
    def from_recorded_event(cls, event: RecordedEvent) -> "RecordedEventResponse":
        values = event.model_dump()
        values["event_location"] = event.event_location()
        return cls.model_validate(values)


class ListRecordedEventsResponse(BaseModel):
    events: list[RecordedEventResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_count: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class RecordedEventCountryCount(BaseModel):
    event_count: int = Field(ge=0)


RecordedEventCountsByCountryResponse: TypeAlias = dict[
    CountryCode | Literal["UNKNOWN"],
    RecordedEventCountryCount,
]


class ListRecordedEventsFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: NonEmptyString | None = None
    tags: list[EventTag] = Field(default_factory=list)
    affected_profession_categories: list[ProfessionCategory] = Field(
        default_factory=list
    )
    response_profession_categories: list[ProfessionCategory] = Field(
        default_factory=list
    )
