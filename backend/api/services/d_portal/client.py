from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any, TypeVar
from urllib.parse import quote

import pycountry
import requests
from pydantic import BaseModel

from api.config import config
from api.services.d_portal.models import (
    D_PORTAL_PUBLIC_BASE_URL,
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
    IatiOrganisation,
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

ACTIVITY_STATUS_NAMES = {
    1: "Pipeline/identification",
    2: "Implementation",
    3: "Completion",
    4: "Post-completion",
    5: "Cancelled",
    6: "Suspended",
}
PARTICIPATING_ORGANISATION_ROLE_NAMES = {
    1: "Funding",
    2: "Accountable",
    3: "Extending",
    4: "Implementing",
}

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
        provider_filters = self._provider_filters(filters)
        count_response = self._query(
            {
                "from": "act",
                "select": "count_aid",
                "limit": -1,
                **provider_filters,
            },
            DPortalQueryResponse[DPortalCountRow],
            malformed_message="d-portal returned malformed search data.",
        )
        activities_response = self._query(
            {
                "from": "act",
                "select": ACTIVITY_SELECT,
                "orderby": "day_start-,aid",
                "limit": filters.limit,
                **provider_filters,
            },
            DPortalQueryResponse[DPortalActivityRow],
            malformed_message="d-portal returned malformed search data.",
        )

        total = count_response.rows[0].count_aid if count_response.rows else 0
        activities = [self._activity_summary(row) for row in activities_response.rows]
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

        country_response = self._query(
            {
                "from": "country",
                "select": "country_code,country_percent",
                "aid": activity_id,
                "limit": DETAIL_RELATION_LIMIT,
            },
            DPortalQueryResponse[DPortalCountryRow],
            malformed_message="d-portal returned malformed activity data.",
        )
        sector_response = self._query(
            {
                "from": "sector",
                "select": "sector_code,sector_group,sector_percent",
                "aid": activity_id,
                "limit": DETAIL_RELATION_LIMIT,
            },
            DPortalQueryResponse[DPortalSectorRow],
            malformed_message="d-portal returned malformed activity data.",
        )
        participating_response = self._xson_query(
            activity_id,
            root=PARTICIPATING_ORGANISATION_ROOT,
            limit=self._max_participating_organisations + 1,
        )
        document_response = self._xson_query(
            activity_id,
            root=DOCUMENT_LINK_ROOT,
            limit=self._max_documents + 1,
        )

        participating_rows = participating_response.rows
        document_rows = document_response.rows
        warnings: list[str] = []
        if len(participating_rows) > self._max_participating_organisations:
            warnings.append("Additional participating organisations were omitted.")
        if len(document_rows) > self._max_documents:
            warnings.append("Additional activity documents were omitted.")

        summary = self._activity_summary(activity_response.rows[0])
        return IatiActivityDetail(
            **summary.model_dump(),
            recipient_countries=[
                self._recipient_country(row) for row in country_response.rows
            ],
            sectors=[self._sector(row) for row in sector_response.rows],
            participating_organisations=[
                self._participating_organisation(row.xson)
                for row in participating_rows[: self._max_participating_organisations]
            ],
            documents=[
                document
                for row in document_rows[: self._max_documents]
                if (document := self._document(row.xson)) is not None
            ],
            warnings=warnings,
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

    @staticmethod
    def _provider_filters(
        filters: SearchIatiActivitiesInput,
    ) -> dict[str, object]:
        values: dict[str, object] = {}
        if filters.query is not None:
            values["text_search"] = filters.query
        if filters.country_codes:
            values["country_code"] = "|".join(filters.country_codes)
        if filters.sector_codes:
            values["sector_code"] = "|".join(filters.sector_codes)
        if filters.sector_group_codes:
            values["sector_group"] = "|".join(filters.sector_group_codes)
        if filters.reporting_organisation_refs:
            values["reporting_ref"] = "|".join(filters.reporting_organisation_refs)
        if filters.humanitarian is not None:
            values["*@humanitarian"] = "1" if filters.humanitarian else "0"
        if filters.active_from_year is not None:
            values["day_end_gt"] = f"{filters.active_from_year}-01-01"
        if filters.active_to_year is not None:
            values["day_start_lteq"] = f"{filters.active_to_year + 1}-01-01"
        return values

    @classmethod
    def _activity_summary(cls, row: DPortalActivityRow) -> IatiActivitySummary:
        return IatiActivitySummary(
            activity_id=row.aid,
            title=cls._clean_string(row.title) or "Untitled IATI activity",
            description=cls._clean_string(row.description),
            reporting_organisation=IatiOrganisation(
                reference=cls._clean_string(row.reporting_ref),
                name=cls._clean_string(row.reporting),
            ),
            status_code=row.status_code,
            status=(
                ACTIVITY_STATUS_NAMES.get(row.status_code)
                if row.status_code is not None
                else None
            ),
            start_date=cls._date_from_days(row.day_start),
            end_date=cls._date_from_days(row.day_end),
            commitment_usd=row.commitment,
            spend_usd=row.spend,
            source_url=cls._activity_url(row.aid),
        )

    @staticmethod
    def _recipient_country(row: DPortalCountryRow) -> IatiRecipientCountry:
        country = pycountry.countries.get(alpha_2=row.country_code)
        return IatiRecipientCountry(
            code=row.country_code,
            name=country.name if country is not None else row.country_code,
            percentage=row.country_percent,
        )

    @staticmethod
    def _sector(row: DPortalSectorRow) -> IatiSector:
        return IatiSector(
            code=row.sector_code,
            group_code=row.sector_group,
            percentage=row.sector_percent,
        )

    @classmethod
    def _participating_organisation(
        cls,
        xson: dict[str, Any],
    ) -> IatiParticipatingOrganisation:
        role_code = cls._optional_int(xson.get("@role"))
        return IatiParticipatingOrganisation(
            reference=cls._clean_string(xson.get("@ref")),
            name=cls._first_narrative(xson.get("/narrative")),
            role_code=role_code,
            role=(
                PARTICIPATING_ORGANISATION_ROLE_NAMES.get(role_code)
                if role_code is not None
                else None
            ),
            type_code=cls._optional_int(xson.get("@type")),
        )

    @classmethod
    def _document(cls, xson: dict[str, Any]) -> IatiDocument | None:
        url = cls._clean_string(xson.get("@url"))
        if url is None:
            return None
        categories = xson.get("/category")
        category_codes: list[str] = []
        if isinstance(categories, list):
            for category in categories:
                if isinstance(category, dict):
                    code = cls._clean_string(category.get("@code"))
                    if code is not None:
                        category_codes.append(code)
        return IatiDocument(
            title=cls._first_narrative(xson.get("/title/narrative")),
            url=url,
            format=cls._clean_string(xson.get("@format")),
            category_codes=list(dict.fromkeys(category_codes)),
        )

    @classmethod
    def _first_narrative(cls, value: Any) -> str | None:
        if isinstance(value, list):
            for item in value:
                narrative = cls._first_narrative(item)
                if narrative is not None:
                    return narrative
            return None
        if isinstance(value, dict):
            direct = cls._clean_string(value.get(""))
            if direct is not None:
                return direct
            return cls._first_narrative(value.get("/narrative"))
        return cls._clean_string(value)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _clean_string(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _date_from_days(days: int | None) -> date | None:
        if days is None:
            return None
        try:
            return date(1970, 1, 1) + timedelta(days=days)
        except OverflowError:
            return None

    @staticmethod
    def _activity_url(activity_id: str) -> str:
        encoded_id = quote(activity_id, safe="")
        return f"{D_PORTAL_PUBLIC_BASE_URL}/ctrack.html#view=act&aid={encoded_id}"
