from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID, uuid4

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, Relationship, SQLModel

from api.models.chat import utc_now

if TYPE_CHECKING:
    from api.models.chat import ChatSession


ProfessionCategory = Literal[
    "medical_clinical",
    "community_health",
    "wash",
    "logistics_supply",
    "surveillance_epidemiology",
    "coordination_cluster",
    "safe_burial_community_response",
    "biomedical_equipment",
    "infrastructure_energy",
    "hq_programme_referent",
    "local_ngo_partner",
    "other",
]


LanguageCode = Literal[
    "ar",
    "bn",
    "de",
    "en",
    "es",
    "fa",
    "fr",
    "hi",
    "id",
    "it",
    "ja",
    "km",
    "ko",
    "lo",
    "ms",
    "my",
    "ne",
    "pa",
    "prs",
    "ps",
    "pt",
    "ru",
    "si",
    "sw",
    "ta",
    "te",
    "th",
    "tl",
    "tr",
    "uk",
    "ur",
    "vi",
    "yue",
    "zh",
]


PROFESSION_CATEGORIES: tuple[ProfessionCategory, ...] = (
    "medical_clinical",
    "community_health",
    "wash",
    "logistics_supply",
    "surveillance_epidemiology",
    "coordination_cluster",
    "safe_burial_community_response",
    "biomedical_equipment",
    "infrastructure_energy",
    "hq_programme_referent",
    "local_ngo_partner",
    "other",
)


LANGUAGE_CODES: tuple[LanguageCode, ...] = (
    "ar",
    "bn",
    "de",
    "en",
    "es",
    "fa",
    "fr",
    "hi",
    "id",
    "it",
    "ja",
    "km",
    "ko",
    "lo",
    "ms",
    "my",
    "ne",
    "pa",
    "prs",
    "ps",
    "pt",
    "ru",
    "si",
    "sw",
    "ta",
    "te",
    "th",
    "tl",
    "tr",
    "uk",
    "ur",
    "vi",
    "yue",
    "zh",
)


class UserProfile(SQLModel, table=True):
    __tablename__ = "userprofile"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    keycloak_sub: str = Field(index=True, unique=True)
    email: str | None = Field(default=None, index=True)
    username: str | None = Field(default=None, index=True)
    first_name: str | None = None
    last_name: str | None = None
    profession: str | None = None
    profession_category: str | None = Field(default=None, index=True)
    center_address: str | None = None
    action_radius_km: float | None = None
    location_extra: str | None = None
    organisation: str | None = None
    mother_tongue: str | None = None
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

    def update_from_editable_fields(self, fields: "UserProfileEditableFields") -> None:
        self.profession = fields.profession
        self.profession_category = fields.profession_category
        self.center_address = fields.center_address
        self.action_radius_km = fields.action_radius_km
        self.location_extra = fields.location_extra
        self.organisation = fields.organisation
        self.mother_tongue = fields.mother_tongue
        self.updated_at = utc_now()


class UserProfileEditableFields(BaseModel):
    profession: str | None = None
    profession_category: ProfessionCategory | None = None
    center_address: str | None = None
    action_radius_km: float | None = PydanticField(default=None, ge=0)
    location_extra: str | None = None
    organisation: str | None = None
    mother_tongue: LanguageCode | None = None


class UserProfileResponse(UserProfileEditableFields):
    id: UUID
    email: str | None
    username: str | None
    first_name: str | None
    last_name: str | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def from_db_model(profile: UserProfile) -> "UserProfileResponse":
        return UserProfileResponse(
            id=profile.id,
            email=profile.email,
            username=profile.username,
            first_name=profile.first_name,
            last_name=profile.last_name,
            profession=profile.profession,
            profession_category=cast(
                ProfessionCategory | None,
                profile.profession_category,
            ),
            center_address=profile.center_address,
            action_radius_km=profile.action_radius_km,
            location_extra=profile.location_extra,
            organisation=profile.organisation,
            mother_tongue=cast(LanguageCode | None, profile.mother_tongue),
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )
