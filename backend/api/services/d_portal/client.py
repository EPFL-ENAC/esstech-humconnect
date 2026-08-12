from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

import requests
from pydantic import BaseModel

from api.config import config
from api.services.d_portal.models import (
    DPortalActivityRow,
    DPortalCountRow,
    DPortalCountryRow,
    DPortalQueryResponse,
    DPortalSectorRow,
    DPortalXsonRow,
    IatiActivityDetail,
    IatiActivitySearchResponse,
    IatiActivitySummary,
    IatiDocument,
    IatiParticipatingOrganisation,
    IatiRecipientCountry,
    IatiSector,
    SearchIatiActivitiesInput,
)
from api.utils.http import post_validated_json

ACTIVITY_SELECT = (
    "aid,reporting,reporting_ref,title,status_code,day_start,day_end,"
    "description,commitment,spend"
)
PARTICIPATING_ORGANISATION_ROOT = "/iati-activities/iati-activity/participating-org"
DOCUMENT_LINK_ROOT = "/iati-activities/iati-activity/document-link"
DETAIL_RELATION_LIMIT = 100

ResponseT = TypeVar("ResponseT", bound=BaseModel)


class DPortalService:
    def __init__(
        self,
        *,
        base_url: str = config.D_PORTAL_BASE_URL,
        user_agent: str = f"HumConnect/1.0 (+{config.APP_URL})",
        timeout_seconds: float = config.D_PORTAL_TIMEOUT_SECONDS,
        max_participating_organisations: int = (
            config.D_PORTAL_MAX_PARTICIPATING_ORGANISATIONS
        ),
        max_documents: int = config.D_PORTAL_MAX_DOCUMENTS,
    ) -> None:
        self._query_url = f"{base_url.rstrip('/')}/q"
        self._headers = {"User-Agent": user_agent}
        self._timeout_seconds = timeout_seconds
        self._max_participating_organisations = max_participating_organisations
        self._max_documents = max_documents

    def search(
        self,
        filters: SearchIatiActivitiesInput,
    ) -> IatiActivitySearchResponse:
        provider_filters = filters.to_api_filters()
        with ThreadPoolExecutor(max_workers=2) as executor:
            count_future = executor.submit(
                self._fetch_search_count,
                provider_filters,
            )
            activities_future = executor.submit(
                self._fetch_search_activities,
                provider_filters,
                filters.limit,
            )
            count_response = count_future.result()
            activities_response = activities_future.result()

        total = count_response.rows[0].count_aid if count_response.rows else 0
        activities = [
            IatiActivitySummary.from_activity_row(row)
            for row in activities_response.rows
        ]
        return IatiActivitySearchResponse(
            total=total,
            returned=len(activities),
            activities=activities,
        )

    def get_activity(self, activity_id: str) -> IatiActivityDetail:
        activity_response = self._query(
            {
                "from": "act",
                "select": ACTIVITY_SELECT,
                "aid": activity_id,
                "limit": 1,
            },
            DPortalQueryResponse[DPortalActivityRow],
            malformed_message="d-portal returned malformed activity data.",
        )
        if not activity_response.rows:
            raise ValueError(f"No d-portal activity was found for '{activity_id}'.")

        with ThreadPoolExecutor(max_workers=4) as executor:
            country_future = executor.submit(
                self._fetch_countries,
                activity_id,
            )
            sector_future = executor.submit(
                self._fetch_sectors,
                activity_id,
            )
            participating_future = executor.submit(
                self._xson_query,
                activity_id,
                root=PARTICIPATING_ORGANISATION_ROOT,
                limit=self._max_participating_organisations + 1,
            )
            document_future = executor.submit(
                self._xson_query,
                activity_id,
                root=DOCUMENT_LINK_ROOT,
                limit=self._max_documents + 1,
            )
            country_response = country_future.result()
            sector_response = sector_future.result()
            participating_response = participating_future.result()
            document_response = document_future.result()

        participating_rows = participating_response.rows
        document_rows = document_response.rows
        warnings: list[str] = []
        if len(participating_rows) > self._max_participating_organisations:
            warnings.append("Additional participating organisations were omitted.")
        if len(document_rows) > self._max_documents:
            warnings.append("Additional activity documents were omitted.")

        summary = IatiActivitySummary.from_activity_row(activity_response.rows[0])
        return IatiActivityDetail(
            **summary.model_dump(),
            recipient_countries=[
                IatiRecipientCountry.from_dportal_country_row(row)
                for row in country_response.rows
            ],
            sectors=[
                IatiSector.from_dportal_sector_row(row) for row in sector_response.rows
            ],
            participating_organisations=[
                IatiParticipatingOrganisation.from_dportal_xson_row(row)
                for row in participating_rows[: self._max_participating_organisations]
            ],
            documents=[
                document
                for row in document_rows[: self._max_documents]
                if (document := IatiDocument.from_dportal_xson_row(row)) is not None
            ],
            warnings=warnings,
        )

    def _fetch_search_count(
        self,
        provider_filters: Mapping[str, object],
    ) -> DPortalQueryResponse[DPortalCountRow]:
        return self._query(
            {
                "from": "act",
                "select": "count_aid",
                "limit": -1,
                **provider_filters,
            },
            DPortalQueryResponse[DPortalCountRow],
            malformed_message="d-portal returned malformed search data.",
        )

    def _fetch_search_activities(
        self,
        provider_filters: Mapping[str, object],
        limit: int,
    ) -> DPortalQueryResponse[DPortalActivityRow]:
        return self._query(
            {
                "from": "act",
                "select": ACTIVITY_SELECT,
                "orderby": "day_start-,aid",
                "limit": limit,
                **provider_filters,
            },
            DPortalQueryResponse[DPortalActivityRow],
            malformed_message="d-portal returned malformed search data.",
        )

    def _fetch_countries(
        self,
        activity_id: str,
    ) -> DPortalQueryResponse[DPortalCountryRow]:
        return self._query(
            {
                "from": "country",
                "select": "country_code,country_percent",
                "aid": activity_id,
                "limit": DETAIL_RELATION_LIMIT,
            },
            DPortalQueryResponse[DPortalCountryRow],
            malformed_message="d-portal returned malformed activity data.",
        )

    def _fetch_sectors(
        self,
        activity_id: str,
    ) -> DPortalQueryResponse[DPortalSectorRow]:
        return self._query(
            {
                "from": "sector",
                "select": "sector_code,sector_group,sector_percent",
                "aid": activity_id,
                "limit": DETAIL_RELATION_LIMIT,
            },
            DPortalQueryResponse[DPortalSectorRow],
            malformed_message="d-portal returned malformed activity data.",
        )

    def _xson_query(
        self,
        activity_id: str,
        *,
        root: str,
        limit: int,
    ) -> DPortalQueryResponse[DPortalXsonRow]:
        return self._query(
            {
                "from": "xson,act",
                "select": "xson",
                "aid": activity_id,
                "root": root,
                "limit": limit,
            },
            DPortalQueryResponse[DPortalXsonRow],
            malformed_message="d-portal returned malformed activity data.",
        )

    def _query(
        self,
        payload: Mapping[str, object],
        model: type[ResponseT],
        *,
        malformed_message: str,
    ) -> ResponseT:
        try:
            return post_validated_json(
                self._query_url,
                model,
                json_body=payload,
                headers=self._headers,
                timeout_seconds=self._timeout_seconds,
                malformed_payload_message=malformed_message,
            )
        except requests.RequestException as exc:
            raise ValueError("d-portal could not be reached.") from exc
