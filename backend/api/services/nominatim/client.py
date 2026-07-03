import asyncio
from logging import getLogger
from typing import Any

import requests

from api.config import config
from api.models.user_profile import AddressSuggestion, UserProfileCoordinates

logger = getLogger(__name__)


def _address_from_properties(properties: dict[str, Any]) -> str:
    address = properties.get("address")
    if not isinstance(address, dict):
        return str(properties.get("display_name") or "").strip()

    parts: list[str] = []
    line = " ".join(
        str(address[key]).strip()
        for key in ["amenity", "office", "road", "house_number"]
        if address.get(key)
    ).strip()
    if line:
        parts.append(line)

    locality = " ".join(
        str(address[key]).strip()
        for key in ["postcode", "village", "town", "city"]
        if address.get(key)
    ).strip()
    if locality:
        parts.append(locality)

    country_code = address.get("country_code")
    if country_code:
        parts.append(str(country_code).upper())

    formatted_address = ", ".join(parts).strip()
    return formatted_address or str(properties.get("display_name") or "").strip()


def _coordinates_from_feature(feature: dict[str, Any]) -> UserProfileCoordinates | None:
    bbox = feature.get("bbox")
    if isinstance(bbox, list) and len(bbox) >= 4:
        try:
            min_lon, min_lat, max_lon, max_lat = [float(value) for value in bbox[:4]]
            return UserProfileCoordinates(
                latitude=min_lat + (max_lat - min_lat) / 2,
                longitude=min_lon + (max_lon - min_lon) / 2,
            )
        except (TypeError, ValueError):
            pass

    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        return None

    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None

    try:
        longitude = float(coordinates[0])
        latitude = float(coordinates[1])
    except (TypeError, ValueError):
        return None

    return UserProfileCoordinates(latitude=latitude, longitude=longitude)


def _suggestion_id(
    properties: dict[str, Any],
    display_name: str,
    coordinates: UserProfileCoordinates,
) -> str:
    osm_type = properties.get("osm_type")
    osm_id = properties.get("osm_id")
    if osm_type and osm_id:
        return f"{osm_type}:{osm_id}"

    return f"{display_name}:{coordinates.latitude}:{coordinates.longitude}"


def suggestions_from_geojson(geojson: dict[str, Any]) -> list[AddressSuggestion]:
    features = geojson.get("features")
    if not isinstance(features, list):
        return []

    suggestions: list[AddressSuggestion] = []
    seen_ids: set[str] = set()
    for feature in features:
        if not isinstance(feature, dict):
            continue

        properties = feature.get("properties")
        if not isinstance(properties, dict):
            continue

        display_name = str(properties.get("display_name") or "").strip()
        if not display_name:
            continue

        coordinates = _coordinates_from_feature(feature)
        if coordinates is None:
            continue

        suggestion_id = _suggestion_id(properties, display_name, coordinates)
        if suggestion_id in seen_ids:
            continue

        address = _address_from_properties(properties)
        suggestions.append(
            AddressSuggestion(
                id=suggestion_id,
                address=address or display_name,
                display_name=display_name,
                latitude=coordinates.latitude,
                longitude=coordinates.longitude,
            )
        )
        seen_ids.add(suggestion_id)

    return suggestions


async def search_address_suggestions(query: str) -> list[AddressSuggestion]:
    normalized_query = query.strip()
    if len(normalized_query) < 3:
        return []

    def request_suggestions() -> list[AddressSuggestion]:
        response = requests.get(
            f"{config.NOMINATIM_BASE_URL.rstrip('/')}/search",
            params={
                "addressdetails": 1,
                "format": "geojson",
                "limit": 5,
                "q": normalized_query,
            },
            headers={
                "User-Agent": f"HumConnect ({config.APP_URL})",
            },
            timeout=config.NOMINATIM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        geojson = response.json()
        if not isinstance(geojson, dict):
            return []
        return suggestions_from_geojson(geojson)

    try:
        return await asyncio.to_thread(request_suggestions)
    except requests.RequestException as exc:
        logger.warning("Could not search address suggestions with Nominatim: %s", exc)
        return []
