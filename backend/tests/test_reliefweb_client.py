import os
from datetime import UTC, datetime

import pytest

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("OPENAI_API_URL", "http://test.local")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("MEDITRON_MCP_API_KEY", "test")
os.environ.setdefault("KEYCLOAK_API_ID", "test")
os.environ.setdefault("KEYCLOAK_API_SECRET", "test")

from api.services.reliefweb import client as reliefweb_client_module
from api.services.humanitarian_context import HumanitarianContextPullStep
from api.services.reliefweb.client import (
    RELIEFWEB_DISASTER_FIELDS,
    RELIEFWEB_REPORT_FIELDS,
    ReliefWebService,
)
from api.services.reliefweb.relief_models import ReliefWebResponse


class FakeReliefWebResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def fixed_now() -> datetime:
    return datetime(2026, 7, 7, 12, 30, 15, 123456, tzinfo=UTC)


def test_reliefweb_service_builds_report_payload():
    service = ReliefWebService(
        context_days=30,
        context_limit=10,
        now_factory=fixed_now,
    )
    filters = service.build_context_filters("Haiti")
    payload = service.build_report_payload(filters)

    assert payload["limit"] == 10
    assert payload["sort"] == ["date.created:desc"]
    assert payload["query"]["value"].startswith("outbreak epidemic")
    assert payload["fields"]["include"] == RELIEFWEB_REPORT_FIELDS
    conditions = {
        condition["field"]: condition["value"]
        for condition in payload["filter"]["conditions"]
    }
    assert conditions["primary_country.name"] == "Haiti"
    assert conditions["date.created"]["from"] == "2026-06-07T12:30:15+00:00"


def test_reliefweb_service_builds_disaster_payload():
    service = ReliefWebService(
        context_days=30,
        context_limit=10,
        now_factory=fixed_now,
    )
    filters = service.build_context_filters("Sudan")
    payload = service.build_disaster_payload(filters)

    assert "query" not in payload
    assert payload["fields"]["include"] == RELIEFWEB_DISASTER_FIELDS
    conditions = {
        condition["field"]: condition["value"]
        for condition in payload["filter"]["conditions"]
    }
    assert conditions["primary_country.name"] == "Sudan"
    assert conditions["status"] == "current"


def test_reliefweb_service_posts_endpoint(monkeypatch):
    calls = []

    def fake_post(url, *, params, json, timeout):
        calls.append((url, params, json, timeout))
        return FakeReliefWebResponse({"data": []})

    monkeypatch.setattr(reliefweb_client_module.requests, "post", fake_post)
    service = ReliefWebService(
        base_url="https://example.test/v2/",
        app_name="test-app",
        timeout_seconds=7,
    )

    result = service.post("/reports", {"limit": 1})

    assert result == ReliefWebResponse(data={"data": []})
    assert calls == [
        (
            "https://example.test/v2/reports",
            {"appname": "test-app"},
            {"limit": 1},
            7,
        )
    ]


def test_reliefweb_service_rejects_malformed_post_payload(monkeypatch):
    def fake_post(url, *, params, json, timeout):
        return FakeReliefWebResponse([])

    monkeypatch.setattr(reliefweb_client_module.requests, "post", fake_post)

    with pytest.raises(ValueError, match="ReliefWeb reports returned a malformed"):
        ReliefWebService().post("reports", {})


def test_humanitarian_context_step_normalizes_reliefweb_items():
    response = ReliefWebResponse(
        data={
            "data": [
                {
                    "id": 123,
                    "fields": {
                        "title": "Cholera outbreak update",
                        "url": "https://example.test/report",
                        "date": {
                            "created": "2026-07-02T12:00:00+00:00",
                            "original": "2026-07-01T12:00:00+00:00",
                        },
                        "primary_country": [{"name": "Haiti"}],
                        "source": [{"name": "WHO"}],
                        "disaster_type": [{"name": "Epidemic"}],
                        "theme": [{"name": "Health"}],
                        "format": [{"name": "Situation Report"}],
                    },
                }
            ]
        }
    )
    step = HumanitarianContextPullStep(
        endpoint="reports",
        item_type="report",
        build_payload=lambda _: {},
        unreachable_warning="ReliefWeb reports could not be reached.",
    )

    result = step.normalize_response(
        response,
        country_name="Haiti",
    )

    assert result.warnings == []
    assert [item.model_dump() for item in result.items] == [
        {
            "provider": "ReliefWeb",
            "type": "report",
            "id": "123",
            "title": "Cholera outbreak update",
            "category": "Epidemic",
            "time": "2026-07-02T12:00:00Z",
            "source_url": "https://example.test/report",
            "sources": ["WHO"],
            "country": "Haiti",
            "location_precision": "country",
        }
    ]


def test_humanitarian_context_step_returns_warning_for_missing_data_list():
    step = HumanitarianContextPullStep(
        endpoint="disasters",
        item_type="disaster",
        build_payload=lambda _: {},
        unreachable_warning="ReliefWeb disasters could not be reached.",
    )

    result = step.normalize_response(
        ReliefWebResponse(data={"not_data": []}),
        country_name="Sudan",
    )

    assert result.items == []
    assert result.warnings == [
        "ReliefWeb disaster response returned no data list."
    ]
