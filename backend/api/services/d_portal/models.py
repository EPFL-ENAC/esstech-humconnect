from datetime import date, timedelta
from typing import Annotated, Any, Generic, TypeVar
from urllib.parse import quote

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

ACTIVITY_STATUS_NAMES = {
    1: "Pipeline/identification",
    2: "Implementation",
    3: "Completion",
    4: "Post-completion",
    5: "Cancelled",
    6: "Suspended",
}
PARTICIPATING_ORGANISATION_ROLE_NAMES = {
    1: "Funding",
    2: "Accountable",
    3: "Extending",
    4: "Implementing",
}

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

    def to_api_filters(self) -> dict[str, object]:
        values: dict[str, object] = {}
        if self.query is not None:
            values["text_search"] = self.query
        if self.country_codes:
            values["country_code"] = "|".join(self.country_codes)
        if self.sector_codes:
            values["sector_code"] = "|".join(self.sector_codes)
        if self.sector_group_codes:
            values["sector_group"] = "|".join(self.sector_group_codes)
        if self.reporting_organisation_refs:
            values["reporting_ref"] = "|".join(self.reporting_organisation_refs)
        if self.humanitarian is not None:
            values["*@humanitarian"] = "1" if self.humanitarian else "0"
        if self.active_from_year is not None:
            values["day_end_gt"] = f"{self.active_from_year}-01-01"
        if self.active_to_year is not None:
            values["day_start_lteq"] = f"{self.active_to_year + 1}-01-01"
        return values

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

    @classmethod
    def from_activity_row(cls, row: DPortalActivityRow) -> "IatiActivitySummary":
        return cls(
            activity_id=row.aid,
            title=_clean_string(row.title) or "Untitled IATI activity",
            description=_clean_string(row.description),
            reporting_organisation=IatiOrganisation(
                reference=_clean_string(row.reporting_ref),
                name=_clean_string(row.reporting),
            ),
            status_code=row.status_code,
            status=(
                ACTIVITY_STATUS_NAMES.get(row.status_code)
                if row.status_code is not None
                else None
            ),
            start_date=_date_from_days(row.day_start),
            end_date=_date_from_days(row.day_end),
            commitment_usd=row.commitment,
            spend_usd=row.spend,
            source_url=_activity_url(row.aid),
        )


class IatiActivitySearchResponse(HumConnectIatiModel):
    total: int = Field(ge=0)
    returned: int = Field(ge=0)
    activities: list[IatiActivitySummary]
    warnings: list[str] = Field(default_factory=list)


class IatiRecipientCountry(HumConnectIatiModel):
    code: str
    name: str
    percentage: float | None

    @classmethod
    def from_dportal_country_row(
        cls,
        row: DPortalCountryRow,
    ) -> "IatiRecipientCountry":
        country = pycountry.countries.get(alpha_2=row.country_code)
        return cls(
            code=row.country_code,
            name=country.name if country is not None else row.country_code,
            percentage=row.country_percent,
        )


class IatiSector(HumConnectIatiModel):
    code: str
    group_code: str | None
    percentage: float | None

    @classmethod
    def from_dportal_sector_row(cls, row: DPortalSectorRow) -> "IatiSector":
        return cls(
            code=row.sector_code,
            group_code=row.sector_group,
            percentage=row.sector_percent,
        )


class IatiParticipatingOrganisation(IatiOrganisation):
    role_code: int | None
    role: str | None
    type_code: int | None

    @classmethod
    def from_dportal_xson_row(
        cls,
        row: DPortalXsonRow,
    ) -> "IatiParticipatingOrganisation":
        role_code = _optional_int(row.xson.get("@role"))
        return cls(
            reference=_clean_string(row.xson.get("@ref")),
            name=_first_narrative(row.xson.get("/narrative")),
            role_code=role_code,
            role=(
                PARTICIPATING_ORGANISATION_ROLE_NAMES.get(role_code)
                if role_code is not None
                else None
            ),
            type_code=_optional_int(row.xson.get("@type")),
        )


class IatiDocument(HumConnectIatiModel):
    title: str | None
    url: str
    format: str | None
    category_codes: list[str]

    @classmethod
    def from_dportal_xson_row(cls, row: DPortalXsonRow) -> "IatiDocument | None":
        url = _clean_string(row.xson.get("@url"))
        if url is None:
            return None

        categories = row.xson.get("/category")
        category_codes: list[str] = []
        if isinstance(categories, list):
            for category in categories:
                if isinstance(category, dict):
                    code = _clean_string(category.get("@code"))
                    if code is not None:
                        category_codes.append(code)
        return cls(
            title=_first_narrative(row.xson.get("/title/narrative")),
            url=url,
            format=_clean_string(row.xson.get("@format")),
            category_codes=list(dict.fromkeys(category_codes)),
        )


class IatiActivityDetail(IatiActivitySummary):
    recipient_countries: list[IatiRecipientCountry]
    sectors: list[IatiSector]
    participating_organisations: list[IatiParticipatingOrganisation]
    documents: list[IatiDocument]
    warnings: list[str] = Field(default_factory=list)


def _first_narrative(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            narrative = _first_narrative(item)
            if narrative is not None:
                return narrative
        return None
    if isinstance(value, dict):
        direct = _clean_string(value.get(""))
        if direct is not None:
            return direct
        return _first_narrative(value.get("/narrative"))
    return _clean_string(value)


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _clean_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _date_from_days(days: int | None) -> date | None:
    if days is None:
        return None
    try:
        return date(1970, 1, 1) + timedelta(days=days)
    except OverflowError:
        return None


def _activity_url(activity_id: str) -> str:
    encoded_id = quote(activity_id, safe="")
    return f"{D_PORTAL_PUBLIC_BASE_URL}/ctrack.html#view=act&aid={encoded_id}"
