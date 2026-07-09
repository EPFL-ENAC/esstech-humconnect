from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import requests
from pydantic import ValidationError

from api.config import config
from api.services.natural_events.models import (
    NasaEonetGeoJsonQueryParams,
    NasaEonetGeoJsonResponse,
    NaturalEventsContextQuery,
    UsgsEarthquakeGeoJsonQueryParams,
    UsgsEarthquakeGeoJsonResponse,
)
from api.utils.geo_utils import bbox_for_radius


class NasaEonetService:
    def __init__(
        self,
        *,
        base_url: str = config.NASA_EONET_BASE_URL,
        timeout_seconds: float = config.NATURAL_EVENTS_TIMEOUT_SECONDS,
        provider_limit: int = config.NATURAL_EVENTS_PROVIDER_LIMIT,
    ) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._provider_limit = provider_limit

    def build_geojson_query_params(
        self,
        query: NaturalEventsContextQuery,
    ) -> NasaEonetGeoJsonQueryParams:
        return NasaEonetGeoJsonQueryParams(
            status="open",
            bbox=bbox_for_radius(
                query.center_latitude,
                query.center_longitude,
                query.radius_km,
            ),
            limit=self._provider_limit,
        )

    def get_events_geojson(
        self,
        params: NasaEonetGeoJsonQueryParams,
    ) -> NasaEonetGeoJsonResponse:
        response = requests.get(
            f"{self._base_url.rstrip('/')}/events/geojson",
            params=params.to_request_params(),
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        try:
            return NasaEonetGeoJsonResponse.model_validate(response.json())
        except ValidationError as exc:
            raise ValueError(
                "NASA EONET returned malformed natural event data."
            ) from exc


class UsgsEarthquakeService:
    def __init__(
        self,
        *,
        base_url: str = config.USGS_EARTHQUAKE_BASE_URL,
        timeout_seconds: float = config.NATURAL_EVENTS_TIMEOUT_SECONDS,
        provider_limit: int = config.NATURAL_EVENTS_PROVIDER_LIMIT,
        earthquake_days: int = config.NATURAL_EVENTS_EARTHQUAKE_DAYS,
        now_factory: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._provider_limit = provider_limit
        self._earthquake_days = earthquake_days
        self._now_factory = now_factory

    def build_geojson_query_params(
        self,
        query: NaturalEventsContextQuery,
    ) -> UsgsEarthquakeGeoJsonQueryParams:
        end_time = self._now_factory()
        start_time = end_time - timedelta(days=self._earthquake_days)
        return UsgsEarthquakeGeoJsonQueryParams(
            latitude=query.center_latitude,
            longitude=query.center_longitude,
            maxradiuskm=query.radius_km,
            starttime=start_time.date(),
            endtime=end_time.date(),
            orderby="time",
            limit=self._provider_limit,
        )

    def query_geojson(
        self,
        params: UsgsEarthquakeGeoJsonQueryParams,
    ) -> UsgsEarthquakeGeoJsonResponse:
        response = requests.get(
            f"{self._base_url.rstrip('/')}/query",
            params=params.to_request_params(),
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        try:
            return UsgsEarthquakeGeoJsonResponse.model_validate(response.json())
        except ValidationError as exc:
            raise ValueError(
                "USGS Earthquake Catalog returned malformed natural event data."
            ) from exc
