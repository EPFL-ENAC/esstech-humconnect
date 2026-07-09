from collections.abc import Callable
from dataclasses import dataclass, field
from logging import getLogger
from typing import Literal, Self

import requests
from pydantic import BaseModel

from api.services.reliefweb import (
    ReliefWebDataEntry,
    ReliefWebRequestPayload,
    ReliefWebResponse,
    ReliefWebService,
)
from api.utils.datetime_utils import parse_provider_datetime, utc_isoformat_z

logger = getLogger(__name__)

HumanitarianContextItemType = Literal["report", "disaster"]


class HumanitarianContextItem(BaseModel):
    provider: str
    type: HumanitarianContextItemType
    id: str
    title: str
    category: str
    time: str | None
    source_url: str | None
    sources: list[str]
    country: str
    location_precision: Literal["country"]

    @classmethod
    def from_reliefweb_data_entry(
        cls,
        entry: ReliefWebDataEntry,
        *,
        item_type: HumanitarianContextItemType,
        country_name: str,
    ) -> Self | None:
        if entry.fields is None:
            return None

        fields = entry.fields
        item_time = fields.created_datetime()
        return cls(
            provider="ReliefWeb",
            type=item_type,
            id=str(entry.id or fields.id or ""),
            title=fields.title_or_name("ReliefWeb item"),
            category=fields.category(item_type),
            time=utc_isoformat_z(item_time),
            source_url=fields.url,
            sources=fields.source_names(),
            country=fields.country_name(country_name),
            location_precision="country",
        )


class HumanitarianContextSummary(BaseModel):
    message: str
    counts: dict[str, int]


class HumanitarianContextResponse(BaseModel):
    summary: HumanitarianContextSummary
    country: str
    items: list[HumanitarianContextItem]
    warnings: list[str] | None = None


@dataclass(frozen=True, slots=True)
class HumanitarianContextPullStepResult:
    items: list[HumanitarianContextItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provider_failed: bool = False
    malformed_payload: bool = False

    @property
    def count(self) -> int:
        return len(self.items)


@dataclass(frozen=True, slots=True)
class HumanitarianContextPullStep:
    endpoint: str
    item_type: HumanitarianContextItemType
    build_payload: Callable[[str], ReliefWebRequestPayload]
    unreachable_warning: str

    def run(
        self,
        *,
        country_name: str,
        reliefweb: ReliefWebService,
    ) -> HumanitarianContextPullStepResult:
        try:
            response = reliefweb.post(
                self.endpoint,
                self.build_payload(country_name),
            )
        except requests.RequestException as exc:
            logger.warning("Could not fetch ReliefWeb %s: %s", self.endpoint, exc)
            return HumanitarianContextPullStepResult(
                warnings=[self.unreachable_warning],
                provider_failed=True,
            )
        except ValueError as exc:
            return HumanitarianContextPullStepResult(
                warnings=[str(exc)],
                malformed_payload=True,
            )

        return self.normalize_response(response, country_name=country_name)

    def normalize_response(
        self,
        response: ReliefWebResponse,
        *,
        country_name: str,
    ) -> HumanitarianContextPullStepResult:
        if response.data.data is None:
            return HumanitarianContextPullStepResult(
                warnings=[
                    f"ReliefWeb {self.item_type} response returned no data list."
                ],
                malformed_payload=True,
            )

        items = [
            item
            for entry in response.data.data
            if (
                item := HumanitarianContextItem.from_reliefweb_data_entry(
                    entry,
                    item_type=self.item_type,
                    country_name=country_name,
                )
            )
            is not None
        ]
        return HumanitarianContextPullStepResult(items=items)


@dataclass(slots=True)
class HumanitarianContextPull:
    country_name: str
    reliefweb: ReliefWebService = field(default_factory=ReliefWebService)
    items: list[HumanitarianContextItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(
        default_factory=lambda: {
            "reports": 0,
            "disasters": 0,
        }
    )
    provider_failures: int = 0
    malformed_payloads: int = 0
    steps: tuple[HumanitarianContextPullStep, ...] = field(init=False)

    def __post_init__(self) -> None:
        self.steps = (
            HumanitarianContextPullStep(
                endpoint="reports",
                item_type="report",
                build_payload=self.reliefweb.build_report_payload,
                unreachable_warning="ReliefWeb reports could not be reached.",
            ),
            HumanitarianContextPullStep(
                endpoint="disasters",
                item_type="disaster",
                build_payload=self.reliefweb.build_disaster_payload,
                unreachable_warning="ReliefWeb disasters could not be reached.",
            ),
        )

    def run(self) -> str:
        for step in self.steps:
            self.add_step_result(
                step,
                step.run(
                    country_name=self.country_name,
                    reliefweb=self.reliefweb,
                ),
            )

        self.raise_for_unusable_result()
        self.items.sort(key=self.item_sort_key, reverse=True)
        return self.to_json()

    def add_step_result(
        self,
        step: HumanitarianContextPullStep,
        result: HumanitarianContextPullStepResult,
    ) -> None:
        self.items.extend(result.items)
        self.warnings.extend(result.warnings)
        self.counts[step.endpoint] = result.count

        if result.provider_failed:
            self.provider_failures += 1
        if result.malformed_payload:
            self.malformed_payloads += 1

    def raise_for_unusable_result(self) -> None:
        if self.provider_failures == len(self.steps):
            raise ValueError("Could not fetch humanitarian context from ReliefWeb.")
        if self.malformed_payloads == len(self.steps):
            raise ValueError("ReliefWeb returned malformed humanitarian context data.")

    def to_json(self) -> str:
        result = HumanitarianContextResponse(
            summary=HumanitarianContextSummary(
                message=(
                    f"Found {len(self.items)} humanitarian context item(s) for "
                    f"{self.country_name}."
                ),
                counts=self.counts,
            ),
            country=self.country_name,
            items=self.items,
        )
        if self.warnings:
            result.warnings = self.warnings

        return result.model_dump_json(indent=2, exclude_none=True)

    def item_sort_key(self, item: HumanitarianContextItem) -> float:
        item_time = parse_provider_datetime(item.time)
        return item_time.timestamp() if item_time is not None else 0.0
