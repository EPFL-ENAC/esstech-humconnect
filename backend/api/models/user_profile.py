from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, Relationship, SQLModel

from api.models.chat import utc_now

if TYPE_CHECKING:
    from api.models.chat import ChatSession


class UserProfile(SQLModel, table=True):
    __tablename__ = "userprofile"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    keycloak_sub: str = Field(index=True, unique=True)
    email: str | None = Field(default=None, index=True)
    username: str | None = Field(default=None, index=True)
    first_name: str | None = None
    last_name: str | None = None
    properties: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    chats: list["ChatSession"] = Relationship(back_populates="user")
