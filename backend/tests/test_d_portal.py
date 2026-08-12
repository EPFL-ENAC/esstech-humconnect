import asyncio
import json
import os
from datetime import date, timedelta
from threading import Barrier

import pytest
import requests
from pydantic import ValidationError

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("OPENAI_API_URL", "http://test.local")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_API_KEY_PREMIUM", "test")
os.environ.setdefault("MEDITRON_MCP_API_KEY", "test")
os.environ.setdefault("KEYCLOAK_API_ID", "test")
os.environ.setdefault("KEYCLOAK_API_SECRET", "test")

from api.services.chat_room.humconnect_assistant import BASE_INSTRUCTIONS
from api.services.chat_room.tools import (
    GET_IATI_ACTIVITY_TOOL,
    SEARCH_IATI_ACTIVITIES_TOOL,
)
from api.services.chat_room.tools import d_portal as d_portal_tool_module
from api.services.d_portal.client import DPortalService
from api.services.d_portal.models import (
    IatiActivityDetail,
    IatiActivitySearchResponse,
    IatiActivitySummary,
    IatiOrganisation,
    SearchIatiActivitiesInput,
)
from api.utils import http as http_utils


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def query_response(rows):
    return {"rows": rows, "count": len(rows), "time": 0.01, "dquery": "SQL"}


def activity_row(**overrides):
    row = {
        "aid": "44000-P120110",
        "reporting": "World Bank",
        "reporting_ref": "44000",
        "title": "Cholera Emergency Response Project",
        "status_code": 3,
        "day_start": 14_992,
        "day_end": 16_159,
        "description": "Emergency response",
        "commitment": 1_500_000,
        "spend": 750_000,
    }
    row.update(overrides)
    return row


def test_search_sends_fixed_queries_and_normalizes_results(monkeypatch):
    calls = []
    request_barrier = Barrier(2)

    def fake_post(url, *, json, headers, timeout):
        calls.append((url, json, headers, timeout))
        request_barrier.wait(timeout=2)
        if json["select"] == "count_aid":
            return FakeResponse(query_response([{"count_aid": "42"}]))
        return FakeResponse(query_response([activity_row()]))

    monkeypatch.setattr(http_utils.requests, "post", fake_post)
    filters = SearchIatiActivitiesInput.model_validate(
        {
            "query": " cholera ",
            "country_codes": ["HT"],
            "sector_codes": ["14030"],
            "sector_group_codes": ["140"],
            "reporting_organisation_refs": ["44000"],
            "humanitarian": True,
            "active_from_year": 2024,
            "active_to_year": 2026,
            "limit": 5,
        }
    )

    result = DPortalService(
        base_url="https://d-portal.test/",
        user_agent="HumConnect/Test",
        timeout_seconds=7,
    ).search(filters)

    provider_filters = {
        "text_search": "cholera",
        "country_code": "HT",
        "sector_code": "14030",
        "sector_group": "140",
        "reporting_ref": "44000",
        "*@humanitarian": "1",
        "day_end_gt": "2024-01-01",
        "day_start_lteq": "2027-01-01",
    }
    calls_by_select = {call[1]["select"]: call for call in calls}
    assert calls_by_select == {
        "count_aid": (
            "https://d-portal.test/q",
            {
                "from": "act",
                "select": "count_aid",
                "limit": -1,
                **provider_filters,
            },
            {"User-Agent": "HumConnect/Test"},
            7,
        ),
        (
            "aid,reporting,reporting_ref,title,status_code,day_start,day_end,"
            "description,commitment,spend"
        ): (
            "https://d-portal.test/q",
            {
                "from": "act",
                "select": (
                    "aid,reporting,reporting_ref,title,status_code,day_start,"
                    "day_end,description,commitment,spend"
                ),
                "orderby": "day_start-,aid",
                "limit": 5,
                **provider_filters,
            },
            {"User-Agent": "HumConnect/Test"},
            7,
        ),
    }
    assert result.total == 42
    assert result.returned == 1
    assert result.warnings == []
    assert result.activities[0].model_dump() == {
        "activity_id": "44000-P120110",
        "title": "Cholera Emergency Response Project",
        "description": "Emergency response",
        "reporting_organisation": {
            "reference": "44000",
            "name": "World Bank",
        },
        "status_code": 3,
        "status": "Completion",
        "start_date": date(1970, 1, 1) + timedelta(days=14_992),
        "end_date": date(1970, 1, 1) + timedelta(days=16_159),
        "commitment_usd": 1_500_000,
        "spend_usd": 750_000,
        "source_url": (
            "https://d-portal.iatistandard.org/ctrack.html#view=act&aid=44000-P120110"
        ),
    }


def test_search_supports_multiple_values_false_flag_and_empty_results(monkeypatch):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append(json)
        if json["select"] == "count_aid":
            return FakeResponse(query_response([]))
        return FakeResponse(query_response([]))

    monkeypatch.setattr(http_utils.requests, "post", fake_post)
    filters = SearchIatiActivitiesInput(
        country_codes=["HT", "SD"],
        sector_codes=["12250", "14030"],
        sector_group_codes=["122", "140"],
        reporting_organisation_refs=["44000", "XM-DAC-41114"],
        humanitarian=False,
    )

    result = DPortalService().search(filters)

    for call in calls:
        assert call["country_code"] == "HT|SD"
        assert call["sector_code"] == "12250|14030"
        assert call["sector_group"] == "122|140"
        assert call["reporting_ref"] == "44000|XM-DAC-41114"
        assert call["*@humanitarian"] == "0"
    assert result.total == 0
    assert result.activities == []


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"limit": 5},
        {"query": ""},
        {"query": "x" * 201},
        {"country_codes": ["ht"]},
        {"country_codes": ["XX"]},
        {"country_codes": ["HT", "HT"]},
        {"country_codes": ["HT"] * 11},
        {"sector_codes": ["140"]},
        {"sector_codes": ["14030", "14030"]},
        {"sector_group_codes": ["14030"]},
        {"reporting_organisation_refs": ["44000", "44000"]},
        {"reporting_organisation_refs": ["44000|XM-DAC-41114"]},
        {"active_from_year": 1959},
        {"active_to_year": date.today().year + 3},
        {"active_from_year": 2026, "active_to_year": 2025},
        {"query": "cholera", "limit": 11},
        {"query": "cholera", "unexpected": True},
    ],
)
def test_search_input_rejects_invalid_arguments(arguments):
    with pytest.raises(ValidationError):
        SearchIatiActivitiesInput.model_validate(arguments)


def test_search_input_strips_query_and_organisation_references():
    result = SearchIatiActivitiesInput(
        query=" cholera ",
        reporting_organisation_refs=[" 44000 "],
    )

    assert result.query == "cholera"
    assert result.reporting_organisation_refs == ["44000"]


def test_detail_uses_bounded_queries_and_normalizes_references(monkeypatch):
    calls = []
    detail_request_barrier = Barrier(4)
    participant_rows = [
        {
            "xson": {
                "@ref": "44002",
                "@role": "1",
                "@type": "40",
                "/narrative": [{"": "International Development Association"}],
            }
        },
        {"xson": {"@ref": "HT-GOV", "@role": "4"}},
    ]
    document_rows = [
        {
            "xson": {
                "@url": "https://example.test/report.pdf",
                "@format": "application/pdf",
                "/title/narrative": [{"": "Project report"}],
                "/category": [{"@code": "A01"}, {"@code": "A01"}],
            }
        },
        {"xson": {"@url": "https://example.test/annex.pdf"}},
    ]

    def fake_post(url, *, json, headers, timeout):
        calls.append(json)
        if json["from"] == "act":
            return FakeResponse(query_response([activity_row()]))
        detail_request_barrier.wait(timeout=2)
        if json["from"] == "country":
            return FakeResponse(
                query_response([{"country_code": "HT", "country_percent": 100}])
            )
        if json["from"] == "sector":
            return FakeResponse(
                query_response(
                    [
                        {
                            "sector_code": "12250",
                            "sector_group": "122",
                            "sector_percent": 100,
                        }
                    ]
                )
            )
        if json["root"].endswith("participating-org"):
            return FakeResponse(query_response(participant_rows))
        return FakeResponse(query_response(document_rows))

    monkeypatch.setattr(http_utils.requests, "post", fake_post)
    result = DPortalService(
        max_participating_organisations=1,
        max_documents=1,
    ).get_activity("44000-P120110")

    assert calls[0] == {
        "from": "act",
        "select": (
            "aid,reporting,reporting_ref,title,status_code,day_start,day_end,"
            "description,commitment,spend"
        ),
        "aid": "44000-P120110",
        "limit": 1,
    }
    detail_calls = {(call["from"], call.get("root")): call for call in calls[1:]}
    assert detail_calls == {
        ("country", None): {
            "from": "country",
            "select": "country_code,country_percent",
            "aid": "44000-P120110",
            "limit": 100,
        },
        ("sector", None): {
            "from": "sector",
            "select": "sector_code,sector_group,sector_percent",
            "aid": "44000-P120110",
            "limit": 100,
        },
        (
            "xson,act",
            "/iati-activities/iati-activity/participating-org",
        ): {
            "from": "xson,act",
            "select": "xson",
            "aid": "44000-P120110",
            "root": "/iati-activities/iati-activity/participating-org",
            "limit": 2,
        },
        ("xson,act", "/iati-activities/iati-activity/document-link"): {
            "from": "xson,act",
            "select": "xson",
            "aid": "44000-P120110",
            "root": "/iati-activities/iati-activity/document-link",
            "limit": 2,
        },
    }
    assert result.recipient_countries[0].model_dump() == {
        "code": "HT",
        "name": "Haiti",
        "percentage": 100.0,
    }
    assert result.sectors[0].model_dump() == {
        "code": "12250",
        "group_code": "122",
        "percentage": 100.0,
    }
    assert result.participating_organisations[0].model_dump() == {
        "reference": "44002",
        "name": "International Development Association",
        "role_code": 1,
        "role": "Funding",
        "type_code": 40,
    }
    assert result.documents[0].model_dump() == {
        "title": "Project report",
        "url": "https://example.test/report.pdf",
        "format": "application/pdf",
        "category_codes": ["A01"],
    }
    assert result.warnings == [
        "Additional participating organisations were omitted.",
        "Additional activity documents were omitted.",
    ]


def test_detail_handles_missing_optional_values_and_invalid_dates(monkeypatch):
    core_response = FakeResponse(
        query_response(
            [
                activity_row(
                    title=" ",
                    reporting=None,
                    reporting_ref=None,
                    description="",
                    status_code=999,
                    day_start=10**30,
                    day_end=None,
                    commitment=None,
                    spend=None,
                )
            ]
        )
    )

    def fake_post(url, *, json, headers, timeout):
        if json["from"] == "act":
            return core_response
        return FakeResponse(query_response([]))

    monkeypatch.setattr(
        http_utils.requests,
        "post",
        fake_post,
    )

    result = DPortalService().get_activity("44000-P120110")

    assert result.title == "Untitled IATI activity"
    assert result.description is None
    assert result.reporting_organisation == IatiOrganisation(
        reference=None,
        name=None,
    )
    assert result.status is None
    assert result.start_date is None
    assert result.end_date is None
    assert result.recipient_countries == []
    assert result.sectors == []
    assert result.participating_organisations == []
    assert result.documents == []


def test_detail_rejects_unknown_activity(monkeypatch):
    monkeypatch.setattr(
        http_utils.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(query_response([])),
    )

    with pytest.raises(
        ValueError,
        match="No d-portal activity was found for 'unknown'",
    ):
        DPortalService().get_activity("unknown")


@pytest.mark.parametrize("payload", [None, [], {}, {"rows": [{}], "count": 1}])
def test_search_rejects_malformed_payloads(monkeypatch, payload):
    monkeypatch.setattr(
        http_utils.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    with pytest.raises(ValueError, match="malformed search data"):
        DPortalService().search(SearchIatiActivitiesInput(query="cholera"))


@pytest.mark.parametrize("failure", ["timeout", "http"])
def test_provider_failures_are_concise(monkeypatch, failure):
    if failure == "timeout":
        monkeypatch.setattr(
            http_utils.requests,
            "post",
            lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout("slow")),
        )
    else:
        monkeypatch.setattr(
            http_utils.requests,
            "post",
            lambda *args, **kwargs: FakeResponse({}, status_code=500),
        )

    with pytest.raises(ValueError, match="d-portal could not be reached"):
        DPortalService().search(SearchIatiActivitiesInput(query="cholera"))


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        (SEARCH_IATI_ACTIVITIES_TOOL, {}, "invalid query data"),
        (
            SEARCH_IATI_ACTIVITIES_TOOL,
            {"query": "cholera", "limit": 11},
            "invalid query data",
        ),
        (GET_IATI_ACTIVITY_TOOL, {"activity_id": ""}, "invalid activity ID"),
        (
            GET_IATI_ACTIVITY_TOOL,
            {"activity_id": "x", "unexpected": True},
            "invalid activity ID",
        ),
    ],
)
def test_iati_tools_reject_invalid_input(tool, arguments, message):
    with pytest.raises(ValueError, match=message):
        asyncio.run(tool.execute(arguments))


def test_search_tool_serializes_result_and_uses_default_limit(monkeypatch):
    calls = []

    class FakeService:
        def search(self, filters):
            calls.append(filters)
            summary = IatiActivitySummary(
                activity_id="activity-1",
                title="Activity",
                description=None,
                reporting_organisation=IatiOrganisation(
                    reference=None,
                    name=None,
                ),
                status_code=None,
                status=None,
                start_date=None,
                end_date=None,
                commitment_usd=None,
                spend_usd=None,
                source_url="https://d-portal.test/activity-1",
            )
            return IatiActivitySearchResponse(
                total=1,
                returned=1,
                activities=[summary],
            )

    monkeypatch.setattr(d_portal_tool_module, "DPortalService", FakeService)

    async def run():
        return await SEARCH_IATI_ACTIVITIES_TOOL.execute(
            {"query": "cholera", "country_codes": ["HT"]},
            None,
        )

    output = asyncio.run(run())

    assert calls[0].limit == 5
    assert calls[0].query == "cholera"
    assert json.loads(output)["activities"][0]["activity_id"] == "activity-1"


def test_detail_tool_serializes_result(monkeypatch):
    calls = []

    class FakeService:
        def get_activity(self, activity_id):
            calls.append(activity_id)
            return IatiActivityDetail(
                activity_id=activity_id,
                title="Activity",
                description=None,
                reporting_organisation=IatiOrganisation(
                    reference=None,
                    name=None,
                ),
                status_code=None,
                status=None,
                start_date=None,
                end_date=None,
                commitment_usd=None,
                spend_usd=None,
                source_url="https://d-portal.test/activity-1",
                recipient_countries=[],
                sectors=[],
                participating_organisations=[],
                documents=[],
            )

    monkeypatch.setattr(d_portal_tool_module, "DPortalService", FakeService)

    async def run():
        return await GET_IATI_ACTIVITY_TOOL.execute(
            {"activity_id": " activity-1 "},
            None,
        )

    output = asyncio.run(run())

    assert calls == ["activity-1"]
    assert json.loads(output)["activity_id"] == "activity-1"


def test_iati_tools_are_registered_and_documented():
    from api.services.chat_room.default_tool_set import DEFAULT_LOCAL_TOOLS

    names = [tool.name for tool in DEFAULT_LOCAL_TOOLS]
    assert "search_iati_activities" in names
    assert "get_iati_activity" in names
    assert "search_iati_activities" in BASE_INSTRUCTIONS
    assert "an activity ID returned by that search" in BASE_INSTRUCTIONS
