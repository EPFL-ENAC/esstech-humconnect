from collections.abc import Callable
from dataclasses import dataclass, field
from logging import getLogger
from typing import Literal, Self
from urllib.parse import urlsplit

import requests
from pydantic import BaseModel

from api.services.provider_pull import ProviderPullCollector, ProviderPullStepResult
from api.services.reliefweb import (
    ReliefWebContextFilters,
    ReliefWebDataEntry,
    ReliefWebRequestPayload,
    ReliefWebResponse,
    ReliefWebService,
)
from api.utils.datetime_utils import parse_provider_datetime, utc_isoformat_z

logger = getLogger(__name__)

HumanitarianContextItemType = Literal["report", "disaster"]


def safe_source_url(value: str | None) -> str | None:
    if not value:
        return None

    try:
        parsed = urlsplit(value)
    except ValueError:
        return None

    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None

    return value


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
            source_url=safe_source_url(fields.url),
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
    filters: ReliefWebContextFilters
    items: list[HumanitarianContextItem]
    warnings: list[str] | None = None


class HumanitarianContextPullStepResult(
    ProviderPullStepResult[HumanitarianContextItem]
):
    pass


@dataclass(frozen=True, slots=True)
class HumanitarianContextPullStep:
    endpoint: str
    item_type: HumanitarianContextItemType
    build_payload: Callable[[ReliefWebContextFilters], ReliefWebRequestPayload]
    unreachable_warning: str

    def run(
        self,
        *,
        filters: ReliefWebContextFilters,
        reliefweb: ReliefWebService,
    ) -> HumanitarianContextPullStepResult:
        try:
            response = reliefweb.post(
                self.endpoint,
                self.build_payload(filters),
            )
        except requests.RequestException as exc:
            logger.warning("Could not fetch ReliefWeb %s: %s", self.endpoint, exc)
            return HumanitarianContextPullStepResult(
                count_key=self.endpoint,
                warnings=[self.unreachable_warning],
                provider_failed=True,
            )
        except ValueError as exc:
            return HumanitarianContextPullStepResult(
                count_key=self.endpoint,
                warnings=[str(exc)],
                malformed_payload=True,
            )

        return self.normalize_response(response, country_name=filters.country)

    def normalize_response(
        self,
        response: ReliefWebResponse,
        *,
        country_name: str,
    ) -> HumanitarianContextPullStepResult:
        if response.data.data is None:
            return HumanitarianContextPullStepResult(
                count_key=self.endpoint,
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
        return HumanitarianContextPullStepResult(count_key=self.endpoint, items=items)


@dataclass(slots=True)
class HumanitarianContextPull:
    country_name: str
    reliefweb: ReliefWebService = field(default_factory=ReliefWebService)
    counts: dict[str, int] = field(
        default_factory=lambda: {
            "reports": 0,
            "disasters": 0,
        }
    )
    steps: tuple[HumanitarianContextPullStep, ...] = field(init=False)
    collector: ProviderPullCollector[HumanitarianContextItem] = field(init=False)
    filters: ReliefWebContextFilters = field(init=False)

    def __post_init__(self) -> None:
        self.filters = self.reliefweb.build_context_filters(self.country_name)
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
        self.collector = ProviderPullCollector(
            all_provider_failure_error=(
                "Could not fetch humanitarian context from ReliefWeb."
            ),
            all_malformed_payload_error=(
                "ReliefWeb returned malformed humanitarian context data."
            ),
            step_count=len(self.steps),
        )

    def run(self) -> str:
        for step in self.steps:
            self.add_step_result(
                step,
                step.run(
                    filters=self.filters,
                    reliefweb=self.reliefweb,
                ),
            )

        self.collector.raise_for_unusable_result()
        self.collector.items.sort(key=self.item_sort_key, reverse=True)
        return self.to_json()

    def add_step_result(
        self,
        step: HumanitarianContextPullStep,
        result: HumanitarianContextPullStepResult,
    ) -> None:
        self.collector.add_result(result)
        self.counts[step.endpoint] = result.count

    def to_json(self) -> str:
        result = HumanitarianContextResponse(
            summary=HumanitarianContextSummary(
                message=(
                    f"Found {len(self.collector.items)} humanitarian context item(s) for "
                    f"{self.country_name}."
                ),
                counts=self.counts,
            ),
            country=self.country_name,
            filters=self.filters,
            items=self.collector.items,
        )
        if self.collector.warnings:
            result.warnings = self.collector.warnings

        return result.model_dump_json(indent=2, exclude_none=True)

    def item_sort_key(self, item: HumanitarianContextItem) -> float:
        item_time = parse_provider_datetime(item.time)
        return item_time.timestamp() if item_time is not None else 0.0
