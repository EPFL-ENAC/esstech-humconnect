import asyncio
import json
from datetime import UTC, datetime, timedelta
from logging import getLogger
from typing import Annotated, Any, cast

import requests
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from api.config import config
from api.services.chat_room.tools.base import (
    HumConnectTool,
    ToolExecutionContext,
    pydantic_response_function_tool,
)
from api.utils.datetime_utils import parse_provider_datetime, utc_isoformat_z

logger = getLogger(__name__)

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
HUMANITARIAN_CONTEXT_QUERY = (
    "outbreak epidemic cholera measles dengue malaria disease health "
    "displacement conflict food insecurity"
)
RELIEFWEB_REPORT_FIELDS = [
    "id",
    "title",
    "url",
    "date",
    "primary_country",
    "source",
    "disaster",
    "disaster_type",
    "theme",
    "format",
]
RELIEFWEB_DISASTER_FIELDS = [
    "id",
    "name",
    "url",
    "date",
    "primary_country",
    "type",
    "status",
]


class HumanitarianContextInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    country_name: NonEmptyString = Field(
        description="Country name to search in ReliefWeb, such as Haiti or Sudan."
    )


def _string_list(values: object, *, key: str = "name") -> list[str]:
    if not isinstance(values, list):
        return []

    output: list[str] = []
    for value in values:
        if isinstance(value, str) and value:
            output.append(value)
        elif isinstance(value, dict):
            item_by_key = cast("dict[str, object]", value)
            item = item_by_key.get(key) or item_by_key.get("title")
            if isinstance(item, str) and item:
                output.append(item)
    return output


def _first_string(values: object, *, key: str = "name") -> str | None:
    strings = _string_list(values, key=key)
    return strings[0] if strings else None


def _country_name(fields: dict[str, Any], fallback: str) -> str:
    countries = fields.get("primary_country")
    if isinstance(countries, list):
        country = _first_string(countries)
        if country:
            return country

    if isinstance(countries, dict):
        country = countries.get("name")
        if isinstance(country, str) and country:
            return country

    return fallback


def _date_from_fields(fields: dict[str, Any]) -> datetime | None:
    date = fields.get("date")
    if not isinstance(date, dict):
        return None

    for key in ["created", "original", "changed"]:
        parsed = parse_provider_datetime(date.get(key))
        if parsed is not None:
            return parsed

    return None


def _category_from_fields(fields: dict[str, Any], fallback: str) -> str:
    disaster_type = _first_string(fields.get("disaster_type"))
    if disaster_type:
        return disaster_type

    primary_type = _first_string(fields.get("primary_type"))
    if primary_type:
        return primary_type

    event_type = _first_string(fields.get("type"))
    if event_type:
        return event_type

    theme = _first_string(fields.get("theme"))
    if theme:
        return theme

    report_format = _first_string(fields.get("format"))
    if report_format:
        return report_format

    disaster = _first_string(fields.get("disaster"))
    if disaster:
        return disaster

    return fallback


def _reliefweb_payload(
    country_name: str,
    *,
    fields: list[str],
    include_query_terms: bool,
    status_filter: str | None = None,
) -> dict[str, Any]:
    start_date = datetime.now(UTC) - timedelta(days=config.HUMANITARIAN_CONTEXT_DAYS)
    filters: list[dict[str, Any]] = [
        {
            "field": "primary_country.name",
            "value": country_name,
        },
        {
            "field": "date.created",
            "value": {
                "from": start_date.replace(microsecond=0).isoformat(),
            },
        },
    ]
    if status_filter is not None:
        filters.append({"field": "status", "value": status_filter})

    payload: dict[str, Any] = {
        "limit": config.HUMANITARIAN_CONTEXT_LIMIT,
        "sort": ["date.created:desc"],
        "fields": {"include": fields},
        "filter": {
            "operator": "AND",
            "conditions": filters,
        },
    }
    if include_query_terms:
        payload["query"] = {"value": HUMANITARIAN_CONTEXT_QUERY}

    return payload


def _reliefweb_post(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        f"{config.RELIEFWEB_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}",
        params={"appname": config.RELIEFWEB_APP_NAME},
        json=payload,
        timeout=config.HUMANITARIAN_CONTEXT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise ValueError(f"ReliefWeb {endpoint} returned a malformed payload.")
    return result


def _normalize_reliefweb_items(
    payload: dict[str, Any],
    *,
    country_name: str,
    item_type: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    data = payload.get("data")
    if not isinstance(data, list):
        return [], [f"ReliefWeb {item_type} response returned no data list."]

    items: list[dict[str, Any]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue

        fields = entry.get("fields")
        if not isinstance(fields, dict):
            continue

        item_time = _date_from_fields(fields)
        items.append(
            {
                "provider": "ReliefWeb",
                "type": item_type,
                "id": str(entry.get("id") or fields.get("id") or ""),
                "title": str(
                    fields.get("title") or fields.get("name") or "ReliefWeb item"
                ),
                "category": _category_from_fields(fields, item_type),
                "time": utc_isoformat_z(item_time),
                "source_url": fields.get("url")
                if isinstance(fields.get("url"), str)
                else None,
                "sources": _string_list(fields.get("source")),
                "country": _country_name(fields, country_name),
                "location_precision": "country",
            }
        )

    return items, []


def _item_sort_key(item: dict[str, Any]) -> float:
    item_time = parse_provider_datetime(item.get("time"))
    return item_time.timestamp() if item_time is not None else 0.0


def _get_humanitarian_context(query: HumanitarianContextInput) -> str:
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    counts = {
        "reports": 0,
        "disasters": 0,
    }
    provider_failures = 0
    malformed_payloads = 0

    try:
        report_payload = _reliefweb_post(
            "reports",
            _reliefweb_payload(
                query.country_name,
                fields=RELIEFWEB_REPORT_FIELDS,
                include_query_terms=True,
            ),
        )
    except requests.RequestException as exc:
        provider_failures += 1
        logger.warning("Could not fetch ReliefWeb reports: %s", exc)
        warnings.append("ReliefWeb reports could not be reached.")
    except ValueError as exc:
        malformed_payloads += 1
        warnings.append(str(exc))
    else:
        report_items, report_warnings = _normalize_reliefweb_items(
            report_payload,
            country_name=query.country_name,
            item_type="report",
        )
        items.extend(report_items)
        warnings.extend(report_warnings)
        counts["reports"] = len(report_items)
        if report_warnings and not report_items:
            malformed_payloads += 1

    try:
        disaster_payload = _reliefweb_post(
            "disasters",
            _reliefweb_payload(
                query.country_name,
                fields=RELIEFWEB_DISASTER_FIELDS,
                include_query_terms=False,
                status_filter="current",
            ),
        )
    except requests.RequestException as exc:
        provider_failures += 1
        logger.warning("Could not fetch ReliefWeb disasters: %s", exc)
        warnings.append("ReliefWeb disasters could not be reached.")
    except ValueError as exc:
        malformed_payloads += 1
        warnings.append(str(exc))
    else:
        disaster_items, disaster_warnings = _normalize_reliefweb_items(
            disaster_payload,
            country_name=query.country_name,
            item_type="disaster",
        )
        items.extend(disaster_items)
        warnings.extend(disaster_warnings)
        counts["disasters"] = len(disaster_items)
        if disaster_warnings and not disaster_items:
            malformed_payloads += 1

    if provider_failures == 2:
        raise ValueError("Could not fetch humanitarian context from ReliefWeb.")
    if malformed_payloads == 2:
        raise ValueError("ReliefWeb returned malformed humanitarian context data.")

    items.sort(key=_item_sort_key, reverse=True)
    result: dict[str, Any] = {
        "summary": {
            "message": (
                f"Found {len(items)} humanitarian context item(s) for "
                f"{query.country_name}."
            ),
            "counts": counts,
        },
        "country": query.country_name,
        "items": items,
    }
    if warnings:
        result["warnings"] = warnings

    return json.dumps(result, indent=2)


async def execute_get_humanitarian_context_tool(
    arguments: dict[str, object],
    context: ToolExecutionContext | None = None,
) -> str:
    try:
        query = HumanitarianContextInput.model_validate(arguments)
    except ValidationError as e:
        raise ValueError(
            f"get_humanitarian_context received invalid query data: {e}"
        ) from e

    return await asyncio.to_thread(_get_humanitarian_context, query)


GET_HUMANITARIAN_CONTEXT_TOOL = HumConnectTool(
    name="get_humanitarian_context",
    label="Get humanitarian context",
    definition=pydantic_response_function_tool(
        HumanitarianContextInput,
        name="get_humanitarian_context",
        description=(
            "Fetch recent country-level humanitarian, outbreak, public-health, "
            "displacement, conflict, and crisis reports from ReliefWeb."
        ),
    ),
    execute=execute_get_humanitarian_context_tool,
)
