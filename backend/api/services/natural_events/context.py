from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from logging import getLogger
from typing import Literal

import requests

from api.services.natural_events.client import NasaEonetService, UsgsEarthquakeService
from api.services.natural_events.models import (
    GeoCoordinate,
    GeoJsonPointGeometry,
    NaturalEventItem,
    NaturalEventsCenter,
    NaturalEventsContextQuery,
    NaturalEventsContextResponse,
    NaturalEventsProviderCounts,
    NaturalEventsSummary,
    event_sort_key,
)
from api.utils.geo_utils import haversine_distance_km

logger = getLogger(__name__)

NaturalEventsProviderKey = Literal["nasa_eonet", "usgs_earthquakes"]


@dataclass(frozen=True, slots=True)
class NearestCoordinate:
    coordinate: GeoCoordinate
    distance_km: float


@dataclass(frozen=True, slots=True)
class NaturalEventsPullStepResult:
    provider_key: NaturalEventsProviderKey
    events: list[NaturalEventItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provider_failed: bool = False
    malformed_payload: bool = False

    @property
    def count(self) -> int:
        return len(self.events)


class NaturalEventsPullStep(ABC):
    unreachable_warning: str
    request_failure_log_message: str

    def __init__(self, query: NaturalEventsContextQuery) -> None:
        self.query = query

    @property
    @abstractmethod
    def provider_key(self) -> NaturalEventsProviderKey:
        pass

    def run(self) -> NaturalEventsPullStepResult:
        try:
            return self.process()
        except requests.RequestException as exc:
            logger.warning(self.request_failure_log_message, exc)
            return NaturalEventsPullStepResult(
                provider_key=self.provider_key,
                warnings=[self.unreachable_warning],
                provider_failed=True,
            )
        except ValueError as exc:
            return NaturalEventsPullStepResult(
                provider_key=self.provider_key,
                warnings=[str(exc)],
                malformed_payload=True,
            )

    @abstractmethod
    def process(self) -> NaturalEventsPullStepResult:
        pass

    def distance_to(self, coordinate: GeoCoordinate) -> float:
        return haversine_distance_km(
            self.query.center_latitude,
            self.query.center_longitude,
            coordinate.latitude,
            coordinate.longitude,
        )


class NasaEonetPullStep(NaturalEventsPullStep):
    unreachable_warning = "NASA EONET could not be reached."
    request_failure_log_message = "Could not fetch NASA EONET natural events: %s"

    def __init__(
        self,
        query: NaturalEventsContextQuery,
        service: NasaEonetService | None = None,
    ) -> None:
        super().__init__(query)
        self.service = service or NasaEonetService()

    @property
    def provider_key(self) -> Literal["nasa_eonet"]:
        return "nasa_eonet"

    def process(self) -> NaturalEventsPullStepResult:
        response = self.service.get_events_geojson(
            self.service.build_geojson_query_params(self.query)
        )

        events: list[NaturalEventItem] = []
        warnings: list[str] = []
        for feature in response.features:
            coordinates = feature.geometry.coordinate_list()
            if not coordinates:
                warnings.append(
                    "NASA EONET returned an event without usable coordinates."
                )
                continue

            nearest = self.nearest_coordinate(coordinates)
            if nearest is None:
                warnings.append(
                    "NASA EONET returned an event without usable coordinates."
                )
                continue

            if isinstance(feature.geometry, GeoJsonPointGeometry):
                if nearest.distance_km > self.query.radius_km:
                    continue
            elif not self.has_coordinate_inside_radius(coordinates):
                continue

            events.append(
                NaturalEventItem.from_nasa_eonet_feature(
                    feature,
                    coordinate=nearest.coordinate,
                    distance_km=nearest.distance_km,
                )
            )

        return NaturalEventsPullStepResult(
            provider_key="nasa_eonet",
            events=events,
            warnings=warnings,
        )

    def nearest_coordinate(
        self, coordinates: list[GeoCoordinate]
    ) -> NearestCoordinate | None:
        if not coordinates:
            return None

        nearest = coordinates[0]
        nearest_distance = self.distance_to(nearest)
        for coordinate in coordinates[1:]:
            distance_km = self.distance_to(coordinate)
            if distance_km < nearest_distance:
                nearest = coordinate
                nearest_distance = distance_km

        return NearestCoordinate(coordinate=nearest, distance_km=nearest_distance)

    def has_coordinate_inside_radius(self, coordinates: list[GeoCoordinate]) -> bool:
        return any(
            self.distance_to(coordinate) <= self.query.radius_km
            for coordinate in coordinates
        )


class UsgsEarthquakePullStep(NaturalEventsPullStep):
    unreachable_warning = "USGS Earthquake Catalog could not be reached."
    request_failure_log_message = "Could not fetch USGS earthquake events: %s"

    def __init__(
        self,
        query: NaturalEventsContextQuery,
        service: UsgsEarthquakeService | None = None,
    ) -> None:
        super().__init__(query)
        self.service = service or UsgsEarthquakeService()

    @property
    def provider_key(self) -> Literal["usgs_earthquakes"]:
        return "usgs_earthquakes"

    def process(self) -> NaturalEventsPullStepResult:
        response = self.service.query_geojson(
            self.service.build_geojson_query_params(self.query)
        )
        return NaturalEventsPullStepResult(
            provider_key="usgs_earthquakes",
            events=[
                NaturalEventItem.from_usgs_earthquake_feature(
                    feature,
                    distance_km=self.distance_to(feature.geometry.coordinates),
                )
                for feature in response.features
            ],
        )


@dataclass(slots=True)
class NaturalEventsContextPull:
    query: NaturalEventsContextQuery
    eonet: NasaEonetService = field(default_factory=NasaEonetService)
    usgs: UsgsEarthquakeService = field(default_factory=UsgsEarthquakeService)
    events: list[NaturalEventItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: NaturalEventsProviderCounts = field(
        default_factory=NaturalEventsProviderCounts
    )
    provider_failures: int = 0
    malformed_payloads: int = 0
    steps: list[NaturalEventsPullStep] = field(init=False)

    def __post_init__(self) -> None:
        self.steps = [
            NasaEonetPullStep(self.query, service=self.eonet),
            UsgsEarthquakePullStep(self.query, service=self.usgs),
        ]

    def run(self) -> str:
        for step in self.steps:
            self.add_step_result(step.run())

        self.raise_for_unusable_result()
        self.events.sort(key=event_sort_key, reverse=True)
        return self.to_json()

    def add_step_result(self, result: NaturalEventsPullStepResult) -> None:
        self.events.extend(result.events)
        self.warnings.extend(result.warnings)
        setattr(self.counts, result.provider_key, result.count)

        if result.provider_failed:
            self.provider_failures += 1
        if result.malformed_payload:
            self.malformed_payloads += 1

    def raise_for_unusable_result(self) -> None:
        if self.provider_failures == len(self.steps):
            raise ValueError("Could not fetch natural events from NASA EONET or USGS.")
        if self.malformed_payloads == len(self.steps):
            raise ValueError(
                "NASA EONET and USGS returned malformed natural event data."
            )

    def to_json(self) -> str:
        response = NaturalEventsContextResponse(
            summary=NaturalEventsSummary(
                message=(
                    f"Found {len(self.events)} natural event(s) near the requested area."
                ),
                counts=self.counts,
            ),
            center=NaturalEventsCenter(
                latitude=self.query.center_latitude,
                longitude=self.query.center_longitude,
                radius_km=self.query.radius_km,
            ),
            events=self.events,
            warnings=self.warnings or None,
        )
        return response.model_dump_json(indent=2, exclude_none=True)
