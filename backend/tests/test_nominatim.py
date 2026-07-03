import asyncio
import os

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("OPENAI_API_URL", "http://test.local")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("MEDITRON_MCP_API_KEY", "test")
os.environ.setdefault("KEYCLOAK_API_ID", "test")
os.environ.setdefault("KEYCLOAK_API_SECRET", "test")

from api.models.user_profile import AddressSuggestion
from api.services.nominatim import client as nominatim_client


class FakeNominatimResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_search_address_suggestions_returns_empty_for_short_query():
    suggestions = asyncio.run(nominatim_client.search_address_suggestions("Ge"))

    assert suggestions == []


def test_search_address_suggestions_maps_nominatim_geojson(monkeypatch):
    def fake_get(url, params, headers, timeout):
        assert url.endswith("/search")
        assert params["format"] == "geojson"
        assert params["addressdetails"] == 1
        assert params["limit"] == 5
        assert params["q"] == "Geneva"
        return FakeNominatimResponse(
            {
                "features": [
                    {
                        "bbox": [6.1, 46.1, 6.2, 46.2],
                        "geometry": {
                            "type": "Point",
                            "coordinates": [6.1432, 46.2044],
                        },
                        "properties": {
                            "address": {
                                "road": "Rue du Mont-Blanc",
                                "house_number": "10",
                                "postcode": "1201",
                                "city": "Geneva",
                                "country_code": "ch",
                            },
                            "display_name": "10, Rue du Mont-Blanc, Geneva, Switzerland",
                            "osm_id": 123,
                            "osm_type": "way",
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(nominatim_client.requests, "get", fake_get)

    suggestions = asyncio.run(nominatim_client.search_address_suggestions("Geneva"))

    assert suggestions == [
        AddressSuggestion(
            id="way:123",
            address="Rue du Mont-Blanc 10, 1201 Geneva, CH",
            display_name="10, Rue du Mont-Blanc, Geneva, Switzerland",
            latitude=46.150000000000006,
            longitude=6.15,
        )
    ]


def test_search_address_suggestions_deduplicates_by_osm_identifier(monkeypatch):
    def fake_get(url, params, headers, timeout):
        return FakeNominatimResponse(
            {
                "features": [
                    {
                        "geometry": {"type": "Point", "coordinates": [6.14, 46.2]},
                        "properties": {
                            "address": {"city": "Geneva", "country_code": "ch"},
                            "display_name": "Geneva, Switzerland",
                            "osm_id": 123,
                            "osm_type": "relation",
                        },
                    },
                    {
                        "geometry": {"type": "Point", "coordinates": [6.15, 46.21]},
                        "properties": {
                            "address": {"city": "Geneva", "country_code": "ch"},
                            "display_name": "Geneva, Switzerland",
                            "osm_id": 123,
                            "osm_type": "relation",
                        },
                    },
                ],
            }
        )

    monkeypatch.setattr(nominatim_client.requests, "get", fake_get)

    suggestions = asyncio.run(nominatim_client.search_address_suggestions("Geneva"))

    assert len(suggestions) == 1
    assert suggestions[0].id == "relation:123"


def test_search_address_suggestions_uses_fallback_id_without_osm_identifier(
    monkeypatch,
):
    def fake_get(url, params, headers, timeout):
        return FakeNominatimResponse(
            {
                "features": [
                    {
                        "geometry": {"type": "Point", "coordinates": [6.14, 46.2]},
                        "properties": {
                            "display_name": "Geneva, Switzerland",
                        },
                    }
                ],
            }
        )

    monkeypatch.setattr(nominatim_client.requests, "get", fake_get)

    suggestions = asyncio.run(nominatim_client.search_address_suggestions("Geneva"))

    assert suggestions == [
        AddressSuggestion(
            id="Geneva, Switzerland:46.2:6.14",
            address="Geneva, Switzerland",
            display_name="Geneva, Switzerland",
            latitude=46.2,
            longitude=6.14,
        )
    ]


def test_search_address_suggestions_returns_empty_on_provider_failure(monkeypatch):
    def fake_get(url, params, headers, timeout):
        raise nominatim_client.requests.RequestException("boom")

    monkeypatch.setattr(nominatim_client.requests, "get", fake_get)

    suggestions = asyncio.run(nominatim_client.search_address_suggestions("Geneva"))

    assert suggestions == []
