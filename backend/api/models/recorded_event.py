import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import JSON, CheckConstraint, Column, DateTime, Float, Index, Text, cast
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
    "food_or_nutrition_insecurity",
    "environmental_hazard",
    "coordination_or_information_gap",
    "community_concern",
    "other",
]


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
    "food_or_nutrition_insecurity",
    "environmental_hazard",
    "coordination_or_information_gap",
    "community_concern",
    "other",
)


class RecordedEvent(SQLModel, table=True):
    __tablename__ = "recordedevent"

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
    event_location: dict[str, Any] = Field(
        sa_column=Column(JSON, nullable=False),
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
        return json.dumps(
            {
                "message": f"Recorded event: {self.event_name}",
                "event": self.model_dump(mode="json"),
            },
            indent=2,
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
    event_location: dict[str, Any]
    tags: list[EventTag]
    keywords: list[str]
    affected_profession_categories: list[ProfessionCategory]
    response_profession_categories: list[ProfessionCategory]
    local_severity: float | None
    country_severity: float | None
    global_severity: float | None
    created_at: datetime


class ListRecordedEventsResponse(BaseModel):
    events: list[RecordedEventResponse]


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
