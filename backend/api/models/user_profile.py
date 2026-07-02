from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
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
    center_latitude: float | None = Field(default=None, ge=-90, le=90)
    center_longitude: float | None = Field(default=None, ge=-180, le=180)
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


class UserProfileCoordinates(BaseModel):
    latitude: float = PydanticField(ge=-90, le=90)
    longitude: float = PydanticField(ge=-180, le=180)


class UserProfileEditableFields(BaseModel):
    profession: str | None = None
    profession_category: ProfessionCategory | None = None
    center_address: str | None = None
    center_coordinates: UserProfileCoordinates | None = None
    action_radius_km: float | None = PydanticField(default=None, ge=0)
    location_extra: str | None = None
    organisation: str | None = None
    mother_tongue: LanguageCode | None = None


class AddressSuggestion(UserProfileCoordinates):
    id: str
    address: str
    display_name: str


class ListAddressSuggestionsResponse(BaseModel):
    suggestions: list[AddressSuggestion]


class UserProfilePromptContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    full_name: str | None = None
    username: str | None = None
    profession: str | None = None
    profession_category: str | None = None
    center_address: str | None = None
    action_radius_km: float | None = None
    location_extra: str | None = None
    organisation: str | None = None
    mother_tongue: str | None = None

    @staticmethod
    def from_db_model(profile: UserProfile) -> "UserProfilePromptContext":
        name_parts = [profile.first_name, profile.last_name]
        full_name = " ".join(
            part.strip() for part in name_parts if part and part.strip()
        )

        return UserProfilePromptContext(
            full_name=full_name or None,
            username=_clean_prompt_value(profile.username),
            profession=_clean_prompt_value(profile.profession),
            profession_category=_clean_prompt_value(profile.profession_category),
            center_address=_clean_prompt_value(profile.center_address),
            action_radius_km=profile.action_radius_km,
            location_extra=_clean_prompt_value(profile.location_extra),
            organisation=_clean_prompt_value(profile.organisation),
            mother_tongue=_clean_prompt_value(profile.mother_tongue),
        )

    def to_prompt_text(self) -> str:
        lines: list[str] = []
        self._append_line(lines, "Name", self.full_name)
        self._append_line(lines, "Username", self.username)
        self._append_line(lines, "Profession", self.profession)
        self._append_line(lines, "Profession category", self.profession_category)
        self._append_line(lines, "Organisation", self.organisation)
        self._append_line(lines, "Mother tongue", self.mother_tongue)
        self._append_line(lines, "Operating location", self.center_address)
        if self.action_radius_km is not None:
            lines.append(f"- Action radius: {self.action_radius_km:g} km")
        self._append_line(lines, "Location notes", self.location_extra)
        return "\n".join(lines)

    @staticmethod
    def _append_line(lines: list[str], label: str, value: str | None) -> None:
        if value:
            lines.append(f"- {label}: {value}")


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
        center_coordinates = None
        if profile.center_latitude is not None and profile.center_longitude is not None:
            center_coordinates = UserProfileCoordinates(
                latitude=profile.center_latitude,
                longitude=profile.center_longitude,
            )

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
            center_coordinates=center_coordinates,
            action_radius_km=profile.action_radius_km,
            location_extra=profile.location_extra,
            organisation=profile.organisation,
            mother_tongue=cast(LanguageCode | None, profile.mother_tongue),
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )


def _clean_prompt_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
