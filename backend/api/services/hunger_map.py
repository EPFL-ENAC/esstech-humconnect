from datetime import date, datetime
from typing import Literal, Self

import pycountry
import requests
from pydantic import BaseModel, ConfigDict, Field, RootModel

from api.config import config
from api.utils.http import fetch_validated_json

HUNGER_MAP_PUBLIC_URL = "https://hungermap.wfp.org/food?w=ipc-phase-3&m=percentage"
PALESTINIAN_WFP_AREAS = {
    "PSG": ("PS", "Gaza"),
    "PSW": ("PS", "West Bank"),
}


class HungerMapProviderModel(BaseModel):
    """Permissive model for the evolving WFP HungerMap API."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class HungerMapCountryPayload(HungerMapProviderModel):
    analysis_date: datetime = Field(alias="analysisDate")
    iso3_code: str = Field(alias="iso3Alpha3")
    reference_period: str = Field(alias="referencePeriod")
    phase_3_plus_percentage: float = Field(alias="phase35Percentage", ge=0)
    phase_3_plus_population: int = Field(alias="phase35Population", ge=0)
    phase_4_plus_percentage: float = Field(alias="phase45Percentage", ge=0)
    phase_4_plus_population: int = Field(alias="phase45Population", ge=0)
    phase_5_percentage: float = Field(alias="phase5Percentage", ge=0)
    phase_5_population: int = Field(alias="phase5Population", ge=0)
    data_source: str = Field(alias="dataSource")


class HungerMapCountryPayloads(RootModel[list[HungerMapCountryPayload]]):
    pass


class HungerMapHeadlinePayload(HungerMapProviderModel):
    date: str
    value: float = Field(ge=0)
    country_count: int = Field(ge=0)
    comment: str


class HungerMapResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HungerMapPhaseEstimate(HungerMapResponseModel):
    percentage: float = Field(ge=0, le=100)
    population: int = Field(ge=0)


class HungerMapCountryEstimate(HungerMapResponseModel):
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    wfp_area_code: str = Field(pattern=r"^[A-Z]{3}$")
    name: str
    reference_period: str
    analysis_date: date
    data_source: str
    phase_3_or_above: HungerMapPhaseEstimate
    phase_4_or_above: HungerMapPhaseEstimate
    phase_5: HungerMapPhaseEstimate

    @classmethod
    def from_payload(cls, payload: HungerMapCountryPayload) -> Self:
        special_area = PALESTINIAN_WFP_AREAS.get(payload.iso3_code)
        if special_area is not None:
            country_code, country_name = special_area
        else:
            country_record = pycountry.countries.get(alpha_3=payload.iso3_code)
            if country_record is None:
                raise ValueError(
                    "WFP HungerMap returned an unknown country code: "
                    f"{payload.iso3_code}."
                )
            country_code = country_record.alpha_2
            country_name = country_record.name

        return cls(
            country_code=country_code,
            wfp_area_code=payload.iso3_code,
            name=country_name,
            reference_period=payload.reference_period,
            analysis_date=payload.analysis_date.date(),
            data_source=payload.data_source,
            phase_3_or_above=HungerMapPhaseEstimate(
                percentage=round(payload.phase_3_plus_percentage * 100, 5),
                population=payload.phase_3_plus_population,
            ),
            phase_4_or_above=HungerMapPhaseEstimate(
                percentage=round(payload.phase_4_plus_percentage * 100, 5),
                population=payload.phase_4_plus_population,
            ),
            phase_5=HungerMapPhaseEstimate(
                percentage=round(payload.phase_5_percentage * 100, 5),
                population=payload.phase_5_population,
            ),
        )


class HungerMapGlobalHeadline(HungerMapResponseModel):
    period: str
    acute_food_insecurity_millions: float = Field(ge=0)
    covered_country_count: int = Field(ge=0)
    source_note: str


class HungerMapResponse(HungerMapResponseModel):
    provider: Literal["WFP HungerMap LIVE"] = "WFP HungerMap LIVE"
    scope: Literal["country", "global"]
    headline: HungerMapGlobalHeadline | None = None
    available_country_estimate_count: int = Field(ge=0)
    countries: list[HungerMapCountryEstimate]
    source_url: str = HUNGER_MAP_PUBLIC_URL
    warnings: list[str] = Field(default_factory=list)


class HungerMapService:
    def __init__(
        self,
        *,
        base_url: str = config.HUNGER_MAP_BASE_URL,
        timeout_seconds: float = config.HUNGER_MAP_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_global_headline(self) -> HungerMapGlobalHeadline:
        payload = fetch_validated_json(
            f"{self._base_url}/ipc/food/insecurity/global/number",
            HungerMapHeadlinePayload,
            timeout_seconds=self._timeout_seconds,
            malformed_payload_message=(
                "WFP HungerMap returned malformed global headline data."
            ),
        )
        return HungerMapGlobalHeadline(
            period=payload.date,
            acute_food_insecurity_millions=payload.value,
            covered_country_count=payload.country_count,
            source_note=payload.comment,
        )

    def get_country_estimates(self) -> list[HungerMapCountryEstimate]:
        payload = fetch_validated_json(
            f"{self._base_url}/ipc/food/insecurity/global/recent",
            HungerMapCountryPayloads,
            timeout_seconds=self._timeout_seconds,
            malformed_payload_message=(
                "WFP HungerMap returned malformed country estimate data."
            ),
        )
        return [HungerMapCountryEstimate.from_payload(item) for item in payload.root]

    def get_context_for_country(self, country: str) -> HungerMapResponse:
        iso3_codes = self._wfp_area_codes_for_country(country)
        try:
            all_estimates = self.get_country_estimates()
        except requests.RequestException as exc:
            raise ValueError(
                "WFP HungerMap country estimates could not be reached."
            ) from exc

        countries = [
            estimate
            for estimate in all_estimates
            if estimate.wfp_area_code in iso3_codes
        ]
        countries.sort(key=lambda estimate: estimate.name)
        warnings: list[str] = []
        if not countries:
            warnings.append(
                f"WFP HungerMap has no current national estimate for {country}."
            )
        elif country in {"PS", "PSE"}:
            warnings.append(
                "WFP HungerMap reports Gaza and the West Bank separately; "
                "these estimates have not been aggregated."
            )

        return HungerMapResponse(
            scope="country",
            available_country_estimate_count=len(all_estimates),
            countries=countries,
            warnings=warnings,
        )

    def get_global_context(self) -> HungerMapResponse:
        headline: HungerMapGlobalHeadline | None = None
        countries: list[HungerMapCountryEstimate] = []
        warnings: list[str] = []
        usable_responses = 0

        try:
            countries = self.get_country_estimates()
            usable_responses += 1
        except requests.RequestException:
            warnings.append("WFP HungerMap country estimates could not be reached.")
        except ValueError as exc:
            warnings.append(str(exc))

        try:
            headline = self.get_global_headline()
            usable_responses += 1
        except requests.RequestException:
            warnings.append("WFP HungerMap global headline could not be reached.")
        except ValueError as exc:
            warnings.append(str(exc))

        if usable_responses == 0:
            raise ValueError("Could not fetch usable data from WFP HungerMap LIVE.")

        countries.sort(
            key=lambda estimate: (
                -estimate.phase_3_or_above.percentage,
                -estimate.phase_3_or_above.population,
                estimate.name,
            )
        )
        return HungerMapResponse(
            scope="global",
            headline=headline,
            available_country_estimate_count=len(countries),
            countries=countries,
            warnings=warnings,
        )

    @staticmethod
    def _wfp_area_codes_for_country(country: str) -> set[str]:
        if country in PALESTINIAN_WFP_AREAS:
            return {country}
        if country in {"PS", "PSE"}:
            return set(PALESTINIAN_WFP_AREAS)

        country_record = (
            pycountry.countries.get(alpha_2=country)
            if len(country) == 2
            else pycountry.countries.get(alpha_3=country)
        )
        if country_record is None:
            raise ValueError(
                "country must be an uppercase ISO 3166-1 alpha-2/alpha-3 code "
                "or a supported WFP area code."
            )
        return {country_record.alpha_3}
