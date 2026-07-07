import asyncio
import json
from datetime import UTC, datetime, timedelta
from logging import getLogger
from typing import Any

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.config import config
from api.services.chat_room.tools.base import (
    HumConnectTool,
    ToolExecutionContext,
    pydantic_response_function_tool,
)
from api.utils.datetime_utils import parse_provider_datetime, utc_isoformat_z
from api.utils.geo_utils import (
    bbox_for_radius,
    coordinate_pairs_from_geojson_coordinates,
    haversine_distance_km,
)

logger = getLogger(__name__)

MAX_RADIUS_KM = 1000.0


class NaturalEventsContextInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    center_latitude: float = Field(ge=-90, le=90)
    center_longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(gt=0, le=MAX_RADIUS_KM)


def _as_float(value: object) -> float | None:
    if not isinstance(value, (int, float, str)):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_source_url(properties: dict[str, Any]) -> str | None:
    link = properties.get("link")
    if isinstance(link, str) and link:
        return link

    sources = properties.get("sources")
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict):
                continue
            source_url = source.get("url") or source.get("link")
            if isinstance(source_url, str) and source_url:
                return source_url

    return None


def _category_titles(properties: dict[str, Any]) -> str | None:
    categories = properties.get("categories")
    if not isinstance(categories, list):
        return None

    titles = [
        str(category.get("title") or category.get("id")).strip()
        for category in categories
        if isinstance(category, dict) and (category.get("title") or category.get("id"))
    ]
    return ", ".join(titles) or None


def _fetch_eonet_events(
    query: NaturalEventsContextInput,
) -> tuple[list[dict[str, Any]], list[str]]:
    response = requests.get(
        f"{config.NASA_EONET_BASE_URL.rstrip('/')}/events/geojson",
        params={
            "status": "open",
            "bbox": bbox_for_radius(
                query.center_latitude,
                query.center_longitude,
                query.radius_km,
            ),
            "limit": config.NATURAL_EVENTS_PROVIDER_LIMIT,
        },
        timeout=config.NATURAL_EVENTS_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return [], ["NASA EONET returned a malformed payload."]

    features = payload.get("features")
    if not isinstance(features, list):
        return [], ["NASA EONET returned no feature list."]

    events: list[dict[str, Any]] = []
    warnings: list[str] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue

        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            continue

        pairs = coordinate_pairs_from_geojson_coordinates(geometry.get("coordinates"))
        if not pairs:
            warnings.append("NASA EONET returned an event without usable coordinates.")
            continue

        distances = [
            haversine_distance_km(
                query.center_latitude,
                query.center_longitude,
                latitude,
                longitude,
            )
            for latitude, longitude in pairs
        ]
        nearest_index, nearest_distance = min(
            enumerate(distances),
            key=lambda item: item[1],
        )
        if geometry.get("type") == "Point" and nearest_distance > query.radius_km:
            continue
        if geometry.get("type") != "Point" and not any(
            distance <= query.radius_km for distance in distances
        ):
            continue

        latitude, longitude = pairs[nearest_index]
        event_time = parse_provider_datetime(properties.get("date"))
        events.append(
            {
                "provider": "NASA EONET",
                "id": str(properties.get("id") or feature.get("id") or ""),
                "title": str(properties.get("title") or "Natural event"),
                "category": _category_titles(properties),
                "time": utc_isoformat_z(event_time),
                "status": "closed" if properties.get("closed") else "open",
                "latitude": latitude,
                "longitude": longitude,
                "distance_km": round(nearest_distance, 1),
                "magnitude": _as_float(properties.get("magnitudeValue")),
                "source_url": _first_source_url(properties),
            }
        )

    return events, warnings


def _fetch_usgs_events(
    query: NaturalEventsContextInput,
) -> tuple[list[dict[str, Any]], list[str]]:
    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(days=config.NATURAL_EVENTS_EARTHQUAKE_DAYS)
    response = requests.get(
        f"{config.USGS_EARTHQUAKE_BASE_URL.rstrip('/')}/query",
        params={
            "format": "geojson",
            "latitude": query.center_latitude,
            "longitude": query.center_longitude,
            "maxradiuskm": query.radius_km,
            "starttime": start_time.date().isoformat(),
            "endtime": end_time.date().isoformat(),
            "orderby": "time",
            "limit": config.NATURAL_EVENTS_PROVIDER_LIMIT,
        },
        timeout=config.NATURAL_EVENTS_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return [], ["USGS Earthquake Catalog returned a malformed payload."]

    features = payload.get("features")
    if not isinstance(features, list):
        return [], ["USGS Earthquake Catalog returned no feature list."]

    events: list[dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue

        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            continue

        pairs = coordinate_pairs_from_geojson_coordinates(geometry.get("coordinates"))
        if not pairs:
            continue

        latitude, longitude = pairs[0]
        distance_km = haversine_distance_km(
            query.center_latitude,
            query.center_longitude,
            latitude,
            longitude,
        )
        events.append(
            {
                "provider": "USGS Earthquake Catalog",
                "id": str(feature.get("id") or properties.get("code") or ""),
                "title": str(
                    properties.get("title") or properties.get("place") or "Earthquake"
                ),
                "category": str(properties.get("type") or "earthquake"),
                "time": utc_isoformat_z(
                    parse_provider_datetime(properties.get("time"))
                ),
                "status": str(properties.get("status") or ""),
                "latitude": latitude,
                "longitude": longitude,
                "distance_km": round(distance_km, 1),
                "magnitude": _as_float(properties.get("mag")),
                "source_url": (
                    properties.get("url")
                    if isinstance(properties.get("url"), str)
                    else None
                ),
            }
        )

    return events, []


def _event_sort_key(event: dict[str, Any]) -> tuple[float, float]:
    magnitude = event.get("magnitude")
    event_time = parse_provider_datetime(event.get("time"))
    return (
        magnitude if isinstance(magnitude, int | float) else -1.0,
        event_time.timestamp() if event_time is not None else 0.0,
    )


def _get_natural_events_context(query: NaturalEventsContextInput) -> str:
    events: list[dict[str, Any]] = []
    warnings: list[str] = []
    provider_counts = {
        "nasa_eonet": 0,
        "usgs_earthquakes": 0,
    }
    provider_failures = 0
    malformed_providers = 0

    try:
        eonet_events, eonet_warnings = _fetch_eonet_events(query)
    except requests.RequestException as exc:
        provider_failures += 1
        logger.warning("Could not fetch NASA EONET natural events: %s", exc)
        warnings.append("NASA EONET could not be reached.")
    else:
        events.extend(eonet_events)
        warnings.extend(eonet_warnings)
        provider_counts["nasa_eonet"] = len(eonet_events)
        if eonet_warnings and not eonet_events:
            malformed_providers += 1

    try:
        usgs_events, usgs_warnings = _fetch_usgs_events(query)
    except requests.RequestException as exc:
        provider_failures += 1
        logger.warning("Could not fetch USGS earthquake events: %s", exc)
        warnings.append("USGS Earthquake Catalog could not be reached.")
    else:
        events.extend(usgs_events)
        warnings.extend(usgs_warnings)
        provider_counts["usgs_earthquakes"] = len(usgs_events)
        if usgs_warnings and not usgs_events:
            malformed_providers += 1

    if provider_failures == 2:
        raise ValueError("Could not fetch natural events from NASA EONET or USGS.")
    if malformed_providers == 2:
        raise ValueError("NASA EONET and USGS returned malformed natural event data.")

    events.sort(key=_event_sort_key, reverse=True)
    result: dict[str, Any] = {
        "summary": {
            "message": f"Found {len(events)} natural event(s) near the requested area.",
            "counts": provider_counts,
        },
        "center": {
            "latitude": query.center_latitude,
            "longitude": query.center_longitude,
            "radius_km": query.radius_km,
        },
        "events": events,
    }
    if warnings:
        result["warnings"] = warnings

    return json.dumps(result, indent=2)


async def execute_get_natural_events_context_tool(
    arguments: dict[str, object],
    context: ToolExecutionContext | None = None,
) -> str:
    try:
        query = NaturalEventsContextInput.model_validate(arguments)
    except ValidationError as e:
        raise ValueError(
            f"get_natural_events_context received invalid query data: {e}"
        ) from e

    return await asyncio.to_thread(_get_natural_events_context, query)


GET_NATURAL_EVENTS_CONTEXT_TOOL = HumConnectTool(
    name="get_natural_events_context",
    label="Get natural events context",
    definition=pydantic_response_function_tool(
        NaturalEventsContextInput,
        name="get_natural_events_context",
        description=(
            "Fetch nearby natural hazard and disaster context from NASA EONET "
            "and the USGS Earthquake Catalog for a center point and radius in km."
        ),
    ),
    execute=execute_get_natural_events_context_tool,
)
