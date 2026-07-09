from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from api.config import config
from api.services.reliefweb.relief_models import (
    ReliefWebFilterCondition,
    ReliefWebRequestPayload,
    ReliefWebResponse,
)

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


class ReliefWebService:
    def __init__(
        self,
        *,
        base_url: str = config.RELIEFWEB_BASE_URL,
        app_name: str = config.RELIEFWEB_APP_NAME,
        timeout_seconds: float = config.HUMANITARIAN_CONTEXT_TIMEOUT_SECONDS,
        context_days: int = config.HUMANITARIAN_CONTEXT_DAYS,
        context_limit: int = config.HUMANITARIAN_CONTEXT_LIMIT,
        now_factory: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._base_url = base_url
        self._app_name = app_name
        self._timeout_seconds = timeout_seconds
        self._context_days = context_days
        self._context_limit = context_limit
        self._now_factory = now_factory

    def build_payload(
        self,
        country_name: str,
        *,
        fields: list[str],
        include_query_terms: bool,
        status_filter: str | None = None,
    ) -> ReliefWebRequestPayload:
        start_date = self._now_factory() - timedelta(days=self._context_days)
        filters: list[ReliefWebFilterCondition] = [
            ReliefWebFilterCondition(
                field="primary_country.name",
                value=country_name,
            ),
            ReliefWebFilterCondition(
                field="date.created",
                value={
                    "from": start_date.replace(microsecond=0).isoformat(),
                },
            ),
        ]
        if status_filter is not None:
            filters.append(
                ReliefWebFilterCondition(field="status", value=status_filter)
            )

        payload: ReliefWebRequestPayload = {
            "limit": self._context_limit,
            "sort": ["date.created:desc"],
            "fields": {"include": fields},
            "filter": {
                "operator": "AND",
                "conditions": [condition.model_dump() for condition in filters],
            },
        }
        if include_query_terms:
            payload["query"] = {"value": HUMANITARIAN_CONTEXT_QUERY}

        return payload

    def build_report_payload(
        self,
        country_name: str,
    ) -> ReliefWebRequestPayload:
        return self.build_payload(
            country_name,
            fields=RELIEFWEB_REPORT_FIELDS,
            include_query_terms=True,
        )

    def build_disaster_payload(
        self,
        country_name: str,
    ) -> ReliefWebRequestPayload:
        return self.build_payload(
            country_name,
            fields=RELIEFWEB_DISASTER_FIELDS,
            include_query_terms=False,
            status_filter="current",
        )

    def post(
        self, endpoint: str, payload: ReliefWebRequestPayload
    ) -> ReliefWebResponse:
        response = requests.post(
            f"{self._base_url.rstrip('/')}/{endpoint.lstrip('/')}",
            params={"appname": self._app_name},
            json=payload,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError(f"ReliefWeb {endpoint} returned a malformed payload.")
        return ReliefWebResponse(data=result)
