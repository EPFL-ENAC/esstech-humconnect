import requests

from api.config import config
from api.services.reliefweb.relief_models import (
    HUMANITARIAN_CONTEXT_QUERY as HUMANITARIAN_CONTEXT_QUERY,
)
from api.services.reliefweb.relief_models import (
    ReliefWebContextFilters,
    ReliefWebRequestPayload,
    ReliefWebResponse,
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
    ) -> None:
        self._base_url = base_url
        self._app_name = app_name
        self._timeout_seconds = timeout_seconds

    def build_payload(
        self,
        filters: ReliefWebContextFilters,
        *,
        fields: list[str],
        include_query_terms: bool,
        status_filter: str | None = None,
    ) -> ReliefWebRequestPayload:
        conditions = filters.to_conditions(status=status_filter)

        payload: ReliefWebRequestPayload = {
            "limit": filters.limit_per_endpoint,
            "sort": list(filters.sort),
            "fields": {"include": fields},
            "filter": {
                "operator": "AND",
                "conditions": [condition.model_dump() for condition in conditions],
            },
        }
        if include_query_terms:
            payload["query"] = {"value": filters.report_query}

        return payload

    def build_report_payload(
        self,
        filters: ReliefWebContextFilters,
    ) -> ReliefWebRequestPayload:
        return self.build_payload(
            filters,
            fields=RELIEFWEB_REPORT_FIELDS,
            include_query_terms=True,
        )

    def build_disaster_payload(
        self,
        filters: ReliefWebContextFilters,
    ) -> ReliefWebRequestPayload:
        return self.build_payload(
            filters,
            fields=RELIEFWEB_DISASTER_FIELDS,
            include_query_terms=False,
            status_filter=filters.disaster_status,
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
