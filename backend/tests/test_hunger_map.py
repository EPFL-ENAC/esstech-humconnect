import asyncio
import json
import os

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
from api.services.chat_room.tools import hunger_map as hunger_map_tool_module
from api.services.chat_room.tools.hunger_map import (
    GET_HUNGER_MAP_CONTEXT_TOOL,
    HungerMapInput,
)
from api.services.hunger_map import (
    HungerMapCountryEstimate,
    HungerMapCountryPayload,
    HungerMapCountryPayloads,
    HungerMapGlobalHeadline,
    HungerMapHeadlinePayload,
    HungerMapService,
)


def make_country_payload(
    iso3_code: str,
    *,
    phase_3_plus_percentage: float,
    phase_3_plus_population: int,
) -> HungerMapCountryPayload:
    return HungerMapCountryPayload.model_validate(
        {
            "analysisDate": "2025-09-15T00:00:00",
            "iso3Alpha3": iso3_code,
            "referencePeriod": "Mar 2026 - Jul 2026 (Projection)",
            "phase35Percentage": phase_3_plus_percentage,
            "phase35Population": phase_3_plus_population,
            "phase45Percentage": 0.18,
            "phase45Population": 1_986_459,
            "phase5Percentage": 0.0,
            "phase5Population": 0,
            "dataSource": "IPC - Sep 2025",
        }
    )


def normalize(
    iso3_code: str,
    *,
    percentage: float = 0.53,
    population: int = 5_910_720,
) -> HungerMapCountryEstimate:
    payload = make_country_payload(
        iso3_code,
        phase_3_plus_percentage=percentage,
        phase_3_plus_population=population,
    )
    return HungerMapCountryEstimate.from_payload(payload)


@pytest.mark.parametrize(
    "country", ["HT", "HTI", "SD", "PS", "PSE", "PSG", "PSW", "global"]
)
def test_hunger_map_input_accepts_supported_selectors(country):
    assert HungerMapInput(country=country).country == country


@pytest.mark.parametrize("country", ["ht", "Global", "ZZ", "ZZZ", "PSX", ""])
def test_hunger_map_input_rejects_invalid_selectors(country):
    with pytest.raises(ValidationError):
        HungerMapInput(country=country)


def test_service_fetches_and_normalizes_country_estimates(monkeypatch):
    calls = []
    service = HungerMapService(base_url="https://example.test/ew/v1", timeout_seconds=7)
    payload = HungerMapCountryPayloads(
        root=[
            make_country_payload(
                "HTI",
                phase_3_plus_percentage=0.53,
                phase_3_plus_population=5_910_720,
            )
        ]
    )

    def fake_fetch(url, model, **kwargs):
        calls.append((url, model, kwargs))
        return payload

    monkeypatch.setattr("api.services.hunger_map.fetch_validated_json", fake_fetch)

    estimates = service.get_country_estimates()

    assert [estimate.model_dump(mode="json") for estimate in estimates] == [
        {
            "country_code": "HT",
            "wfp_area_code": "HTI",
            "name": "Haiti",
            "reference_period": "Mar 2026 - Jul 2026 (Projection)",
            "analysis_date": "2025-09-15",
            "data_source": "IPC - Sep 2025",
            "phase_3_or_above": {
                "percentage": 53.0,
                "population": 5_910_720,
            },
            "phase_4_or_above": {
                "percentage": 18.0,
                "population": 1_986_459,
            },
            "phase_5": {"percentage": 0.0, "population": 0},
        }
    ]
    assert calls == [
        (
            "https://example.test/ew/v1/ipc/food/insecurity/global/recent",
            HungerMapCountryPayloads,
            {
                "timeout_seconds": 7,
                "malformed_payload_message": (
                    "WFP HungerMap returned malformed country estimate data."
                ),
            },
        )
    ]


def test_service_fetches_and_normalizes_global_headline(monkeypatch):
    calls = []
    service = HungerMapService(base_url="https://example.test/ew/v1", timeout_seconds=7)
    payload = HungerMapHeadlinePayload(
        date="2025-11",
        value=318.0,
        country_count=68,
        comment="WFP 2026 Global Outlook",
    )

    def fake_fetch(url, model, **kwargs):
        calls.append((url, model, kwargs))
        return payload

    monkeypatch.setattr("api.services.hunger_map.fetch_validated_json", fake_fetch)

    headline = service.get_global_headline()

    assert headline == HungerMapGlobalHeadline(
        period="2025-11",
        acute_food_insecurity_millions=318.0,
        covered_country_count=68,
        source_note="WFP 2026 Global Outlook",
    )
    assert calls == [
        (
            "https://example.test/ew/v1/ipc/food/insecurity/global/number",
            HungerMapHeadlinePayload,
            {
                "timeout_seconds": 7,
                "malformed_payload_message": (
                    "WFP HungerMap returned malformed global headline data."
                ),
            },
        )
    ]


def test_country_context_filters_by_iso_alpha_2(monkeypatch):
    service = HungerMapService()
    estimates = [normalize("HTI"), normalize("SDN")]
    monkeypatch.setattr(service, "get_country_estimates", lambda: estimates)

    response = service.get_context_for_country("HT")

    assert response.scope == "country"
    assert response.headline is None
    assert response.available_country_estimate_count == 2
    assert [item.wfp_area_code for item in response.countries] == ["HTI"]
    assert response.warnings == []


@pytest.mark.parametrize("country", ["PS", "PSE"])
def test_palestine_context_keeps_wfp_areas_separate(monkeypatch, country):
    service = HungerMapService()
    estimates = [normalize("PSG"), normalize("PSW")]
    monkeypatch.setattr(service, "get_country_estimates", lambda: estimates)

    response = service.get_context_for_country(country)

    assert [(item.country_code, item.name) for item in response.countries] == [
        ("PS", "Gaza"),
        ("PS", "West Bank"),
    ]
    assert response.warnings == [
        "WFP HungerMap reports Gaza and the West Bank separately; "
        "these estimates have not been aggregated."
    ]


@pytest.mark.parametrize(
    ("country", "expected_area"),
    [("HTI", "HTI"), ("PSG", "PSG"), ("PSW", "PSW")],
)
def test_country_context_accepts_alpha_3_and_wfp_area_codes(
    monkeypatch, country, expected_area
):
    service = HungerMapService()
    estimates = [normalize("HTI"), normalize("PSG"), normalize("PSW")]
    monkeypatch.setattr(service, "get_country_estimates", lambda: estimates)

    response = service.get_context_for_country(country)

    assert [item.wfp_area_code for item in response.countries] == [expected_area]
    assert response.warnings == []


def test_country_context_returns_coverage_warning_when_no_estimate(monkeypatch):
    service = HungerMapService()
    monkeypatch.setattr(service, "get_country_estimates", lambda: [])

    response = service.get_context_for_country("CH")

    assert response.countries == []
    assert response.warnings == [
        "WFP HungerMap has no current national estimate for CH."
    ]


def test_global_context_returns_headline_and_all_countries_sorted(monkeypatch):
    service = HungerMapService()
    estimates = [
        normalize("HTI", percentage=0.53, population=5_910_720),
        normalize("SDN", percentage=0.67, population=5_574_076),
        normalize("AFG", percentage=0.28, population=13_778_381),
    ]
    headline = HungerMapGlobalHeadline(
        period="2025-11",
        acute_food_insecurity_millions=318.0,
        covered_country_count=68,
        source_note="WFP 2026 Global Outlook",
    )
    monkeypatch.setattr(service, "get_country_estimates", lambda: estimates)
    monkeypatch.setattr(service, "get_global_headline", lambda: headline)

    response = service.get_global_context()

    assert response.headline == headline
    assert response.available_country_estimate_count == 3
    assert [item.wfp_area_code for item in response.countries] == [
        "SDN",
        "HTI",
        "AFG",
    ]
    assert response.warnings == []


def test_global_context_returns_partial_result_with_warning(monkeypatch):
    service = HungerMapService()
    estimates = [normalize("HTI")]
    monkeypatch.setattr(service, "get_country_estimates", lambda: estimates)

    def fail_headline():
        raise requests.Timeout("slow")

    monkeypatch.setattr(service, "get_global_headline", fail_headline)

    response = service.get_global_context()

    assert response.headline is None
    assert response.countries == estimates
    assert response.warnings == ["WFP HungerMap global headline could not be reached."]


def test_global_context_fails_when_both_responses_are_unusable(monkeypatch):
    service = HungerMapService()

    def fail():
        raise requests.Timeout("slow")

    monkeypatch.setattr(service, "get_country_estimates", fail)
    monkeypatch.setattr(service, "get_global_headline", fail)

    with pytest.raises(ValueError, match="Could not fetch usable data"):
        service.get_global_context()


def test_hunger_map_tool_delegates_to_service(monkeypatch):
    calls = []

    class FakeService:
        def get_context_for_country(self, country):
            calls.append(("country", country))
            return HungerMapServiceResponseStub("country")

        def get_global_context(self):
            calls.append(("global", None))
            return HungerMapServiceResponseStub("global")

    class HungerMapServiceResponseStub:
        def __init__(self, scope):
            self.scope = scope

        def model_dump_json(self, *, indent, exclude_none):
            assert indent == 2
            assert exclude_none is True
            return json.dumps({"scope": self.scope})

    monkeypatch.setattr(hunger_map_tool_module, "HungerMapService", FakeService)

    async def run(country):
        return await GET_HUNGER_MAP_CONTEXT_TOOL.execute({"country": country}, None)

    country_result = asyncio.run(run("PSW"))
    global_result = asyncio.run(run("global"))

    assert calls == [("country", "PSW"), ("global", None)]
    assert json.loads(country_result) == {"scope": "country"}
    assert json.loads(global_result) == {"scope": "global"}


def test_hunger_map_tool_is_registered_and_routed():
    from api.services.chat_room.default_tool_set import DEFAULT_LOCAL_TOOLS

    names = [tool.name for tool in DEFAULT_LOCAL_TOOLS]
    assert "get_hunger_map_context" in names
    assert "IPC/CH acute food-insecurity statistics" in BASE_INSTRUCTIONS
    assert "'global' for the headline" in BASE_INSTRUCTIONS
