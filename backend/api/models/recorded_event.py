import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

from api.models.user_profile import ProfessionCategory
from api.utils.datetime_utils import utc_now

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
        sa_column=Column(JSON, nullable=False),
    )
    keywords: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    affected_profession_categories: list[ProfessionCategory] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    response_profession_categories: list[ProfessionCategory] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
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
    created_at: datetime


class ListRecordedEventsResponse(BaseModel):
    events: list[RecordedEventResponse]
