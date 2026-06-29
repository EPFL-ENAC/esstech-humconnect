import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

from api.models.chat import utc_now


class RecordedEvent(SQLModel, table=True):
    __tablename__ = "recordedevent"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    chat_id: UUID = Field(foreign_key="chatsession.id", index=True)
    initiated_by_client_id: str = Field(index=True)
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
    tags: list[str] = Field(
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
    initiated_by_client_id: str
    source_message_id: UUID
    original_text: str
    event_name: str
    event_datetime: datetime | None
    event_date_granularity: str
    event_date_precision: str
    event_date_input: dict[str, Any]
    event_location: dict[str, Any]
    tags: list[str]
    created_at: datetime


class ListRecordedEventsResponse(BaseModel):
    events: list[RecordedEventResponse]
