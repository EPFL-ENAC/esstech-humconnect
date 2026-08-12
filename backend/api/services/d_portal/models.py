from datetime import date
from typing import Annotated, Any, Generic, TypeVar

import pycountry
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from api.config import config
from api.utils.pydantic_types import NonEmptyString

D_PORTAL_PUBLIC_BASE_URL = "https://d-portal.iatistandard.org"

BoundedSearchText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


class SearchIatiActivitiesInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: BoundedSearchText | None = Field(
        default=None,
        description=(
            "Keywords to search in IATI activity narratives, such as cholera or "
            "flood response."
        ),
    )
    country_codes: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Unique uppercase ISO 3166-1 alpha-2 recipient-country codes.",
    )
    sector_codes: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Unique five-digit OECD DAC sector codes.",
    )
    sector_group_codes: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Unique three-digit OECD DAC sector-group codes.",
    )
    reporting_organisation_refs: list[NonEmptyString] = Field(
        default_factory=list,
        max_length=10,
        description="Unique IATI reporting-organisation references.",
    )
    humanitarian: bool | None = Field(
        default=None,
        description="Filter on the IATI humanitarian activity flag.",
    )
    active_from_year: int | None = Field(
        default=None,
        description="Earliest year overlapped by the activity.",
    )
    active_to_year: int | None = Field(
        default=None,
        description="Latest year overlapped by the activity.",
    )
    limit: int = Field(
        default=config.D_PORTAL_SEARCH_LIMIT,
        ge=1,
        le=10,
        description="Maximum number of activities to return.",
    )

    @field_validator("country_codes")
    @classmethod
    def validate_country_codes(cls, values: list[str]) -> list[str]:
        cls._require_unique(values, "country_codes")
        for value in values:
            if (
                len(value) != 2
                or value != value.upper()
                or pycountry.countries.get(alpha_2=value) is None
            ):
                raise ValueError(
                    "country_codes must contain uppercase ISO 3166-1 alpha-2 codes"
                )
        return values

    @field_validator("sector_codes")
    @classmethod
    def validate_sector_codes(cls, values: list[str]) -> list[str]:
        cls._require_unique(values, "sector_codes")
        if any(len(value) != 5 or not value.isdigit() for value in values):
            raise ValueError("sector_codes must contain five-digit OECD DAC codes")
        return values

    @field_validator("sector_group_codes")
    @classmethod
    def validate_sector_group_codes(cls, values: list[str]) -> list[str]:
        cls._require_unique(values, "sector_group_codes")
        if any(len(value) != 3 or not value.isdigit() for value in values):
            raise ValueError(
                "sector_group_codes must contain three-digit OECD DAC codes"
            )
        return values

    @field_validator("reporting_organisation_refs")
    @classmethod
    def validate_reporting_organisation_refs(cls, values: list[str]) -> list[str]:
        cls._require_unique(values, "reporting_organisation_refs")
        if any("|" in value or "," in value for value in values):
            raise ValueError(
                "reporting_organisation_refs cannot contain list separators"
            )
        return values

    @field_validator("active_from_year", "active_to_year")
    @classmethod
    def validate_year(cls, value: int | None) -> int | None:
        if value is not None and not 1960 <= value <= date.today().year + 2:
            raise ValueError(
                f"activity years must be between 1960 and {date.today().year + 2}"
            )
        return value

    @model_validator(mode="after")
    def validate_search(self) -> "SearchIatiActivitiesInput":
        has_criterion = any(
            [
                self.query is not None,
                bool(self.country_codes),
                bool(self.sector_codes),
                bool(self.sector_group_codes),
                bool(self.reporting_organisation_refs),
                self.humanitarian is not None,
                self.active_from_year is not None,
                self.active_to_year is not None,
            ]
        )
        if not has_criterion:
            raise ValueError("at least one IATI search criterion is required")
        if (
            self.active_from_year is not None
            and self.active_to_year is not None
            and self.active_from_year > self.active_to_year
        ):
            raise ValueError("active_from_year cannot be after active_to_year")
        return self

    @staticmethod
    def _require_unique(values: list[str], field_name: str) -> None:
        if len(values) != len(set(values)):
            raise ValueError(f"{field_name} must contain unique values")


class GetIatiActivityInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    activity_id: NonEmptyString = Field(
        description="IATI activity identifier returned by search_iati_activities."
    )


class DPortalProviderModel(BaseModel):
    """Permissive model for d-portal's evolving response format."""

    model_config = ConfigDict(extra="allow")


class DPortalActivityRow(DPortalProviderModel):
    aid: str
    reporting: str | None = None
    reporting_ref: str | None = None
    title: str | None = None
    status_code: int | None = None
    day_start: int | None = None
    day_end: int | None = None
    description: str | None = None
    commitment: float | None = None
    spend: float | None = None


class DPortalCountRow(DPortalProviderModel):
    count_aid: int = Field(ge=0)


class DPortalCountryRow(DPortalProviderModel):
    country_code: str
    country_percent: float | None = None


class DPortalSectorRow(DPortalProviderModel):
    sector_code: str
    sector_group: str | None = None
    sector_percent: float | None = None


class DPortalXsonRow(DPortalProviderModel):
    xson: dict[str, Any]


RowT = TypeVar("RowT", bound=DPortalProviderModel)


class DPortalQueryResponse(DPortalProviderModel, Generic[RowT]):
    rows: list[RowT]
    count: int = Field(ge=0)


class HumConnectIatiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IatiOrganisation(HumConnectIatiModel):
    reference: str | None
    name: str | None


class IatiActivitySummary(HumConnectIatiModel):
    activity_id: str
    title: str
    description: str | None
    reporting_organisation: IatiOrganisation
    status_code: int | None
    status: str | None
    start_date: date | None
    end_date: date | None
    commitment_usd: float | None
    spend_usd: float | None
    source_url: str


class IatiActivitySearchResponse(HumConnectIatiModel):
    total: int = Field(ge=0)
    returned: int = Field(ge=0)
    activities: list[IatiActivitySummary]
    warnings: list[str] = Field(default_factory=list)


class IatiRecipientCountry(HumConnectIatiModel):
    code: str
    name: str
    percentage: float | None


class IatiSector(HumConnectIatiModel):
    code: str
    group_code: str | None
    percentage: float | None


class IatiParticipatingOrganisation(IatiOrganisation):
    role_code: int | None
    role: str | None
    type_code: int | None


class IatiDocument(HumConnectIatiModel):
    title: str | None
    url: str
    format: str | None
    category_codes: list[str]


class IatiActivityDetail(IatiActivitySummary):
    recipient_countries: list[IatiRecipientCountry]
    sectors: list[IatiSector]
    participating_organisations: list[IatiParticipatingOrganisation]
    documents: list[IatiDocument]
    warnings: list[str] = Field(default_factory=list)
