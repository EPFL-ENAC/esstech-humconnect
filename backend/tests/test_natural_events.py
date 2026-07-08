import json
import os
from datetime import UTC, datetime

import pytest
import requests

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("OPENAI_API_URL", "http://test.local")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("MEDITRON_MCP_API_KEY", "test")
os.environ.setdefault("KEYCLOAK_API_ID", "test")
os.environ.setdefault("KEYCLOAK_API_SECRET", "test")

from api.services.natural_events import client as natural_events_client_module
from api.services.natural_events import (
    NasaEonetPullStep,
    NasaEonetService,
    NaturalEventsContextPull,
    NaturalEventsContextQuery,
    UsgsEarthquakePullStep,
    UsgsEarthquakeService,
)
from api.services.natural_events.models import (
    GeoCoordinate,
    GeoJsonPointGeometry,
    GeoJsonPolygonGeometry,
    NasaEonetFeature,
    NasaEonetGeoJsonResponse,
    NasaEonetProperties,
    UsgsEarthquakeFeature,
    UsgsEarthquakeGeoJsonResponse,
    UsgsEarthquakeProperties,
)


class FakeProviderResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def fixed_now() -> datetime:
    return datetime(2026, 7, 8, 12, 0, tzinfo=UTC)


def context_query() -> NaturalEventsContextQuery:
    return NaturalEventsContextQuery(
        center_latitude=46.0,
        center_longitude=7.0,
        radius_km=100.0,
    )


def test_nasa_eonet_service_builds_and_sends_typed_query_params(monkeypatch):
    calls = []

    def fake_get(url, *, params, timeout):
        calls.append((url, params, timeout))
        return FakeProviderResponse({"features": []})

    monkeypatch.setattr(natural_events_client_module.requests, "get", fake_get)
    service = NasaEonetService(
        base_url="https://eonet.example/api/v3/",
        timeout_seconds=7,
        provider_limit=3,
    )

    params = service.build_geojson_query_params(context_query())
    result = service.get_events_geojson(params)

    assert result == NasaEonetGeoJsonResponse(features=[])
    assert params.status == "open"
    assert params.limit == 3
    assert len(params.bbox.split(",")) == 4
    assert calls == [
        (
            "https://eonet.example/api/v3/events/geojson",
            params.to_request_params(),
            7,
        )
    ]


def test_usgs_service_builds_and_sends_typed_query_params(monkeypatch):
    calls = []

    def fake_get(url, *, params, timeout):
        calls.append((url, params, timeout))
        return FakeProviderResponse({"features": []})

    monkeypatch.setattr(natural_events_client_module.requests, "get", fake_get)
    service = UsgsEarthquakeService(
        base_url="https://earthquake.example/fdsnws/event/1/",
        timeout_seconds=8,
        provider_limit=4,
        earthquake_days=30,
        now_factory=fixed_now,
    )

    params = service.build_geojson_query_params(context_query())
    result = service.query_geojson(params)

    assert result == UsgsEarthquakeGeoJsonResponse(features=[])
    assert params.format == "geojson"
    assert params.latitude == 46.0
    assert params.longitude == 7.0
    assert params.maxradiuskm == 100.0
    assert params.starttime.isoformat() == "2026-06-08"
    assert params.endtime.isoformat() == "2026-07-08"
    assert params.orderby == "time"
    assert params.limit == 4
    assert calls == [
        (
            "https://earthquake.example/fdsnws/event/1/query",
            params.to_request_params(),
            8,
        )
    ]


def test_natural_events_pull_normalizes_and_sorts_provider_events():
    eonet_response = NasaEonetGeoJsonResponse(
        features=[
            {
                "id": "EONET_1",
                "properties": {
                    "id": "EONET_1",
                    "title": "Wildfire near Lausanne",
                    "date": "2026-07-02T12:00:00Z",
                    "categories": [{"id": "wildfires", "title": "Wildfires"}],
                    "sources": [{"url": "https://example.test/eonet"}],
                },
                "geometry": {"type": "Point", "coordinates": [7.01, 46.01]},
            },
            {
                "id": "EONET_OUTSIDE",
                "properties": {
                    "id": "EONET_OUTSIDE",
                    "title": "Distant storm",
                    "date": "2026-07-02T12:00:00Z",
                    "categories": [{"id": "severeStorms"}],
                },
                "geometry": {"type": "Point", "coordinates": [7.0, 48.0]},
            },
        ]
    )
    usgs_response = UsgsEarthquakeGeoJsonResponse(
        features=[
            {
                "id": "us7000abcd",
                "properties": {
                    "title": "M 4.5 - Switzerland",
                    "type": "earthquake",
                    "time": 1783000000000,
                    "status": "reviewed",
                    "mag": 4.5,
                    "url": "https://example.test/usgs",
                    "magType": "mb",
                },
                "geometry": {"type": "Point", "coordinates": [7.2, 46.2, 10.0]},
            }
        ]
    )

    pull = NaturalEventsContextPull(
        context_query(),
        eonet=FakeEonetService(eonet_response),
        usgs=FakeUsgsService(usgs_response),
    )

    result = json.loads(pull.run())

    assert result["summary"]["counts"] == {
        "nasa_eonet": 1,
        "usgs_earthquakes": 1,
    }
    assert result["center"] == {
        "latitude": 46.0,
        "longitude": 7.0,
        "radius_km": 100.0,
    }
    assert [event["id"] for event in result["events"]] == [
        "us7000abcd",
        "EONET_1",
    ]
    assert result["events"][0]["provider"] == "USGS Earthquake Catalog"
    assert result["events"][0]["magnitude"] == 4.5
    assert result["events"][1]["provider"] == "NASA EONET"
    assert result["events"][1]["category"] == "Wildfires"
    assert result["events"][1]["source_url"] == "https://example.test/eonet"
    assert all(event["id"] != "EONET_OUTSIDE" for event in result["events"])


def test_eonet_step_processes_its_own_service_response():
    response = NasaEonetGeoJsonResponse(
        features=[
            {
                "id": "EONET_1",
                "properties": {
                    "id": "EONET_1",
                    "title": "Wildfire near Lausanne",
                    "date": "2026-07-02T12:00:00Z",
                    "categories": [{"id": "wildfires", "title": "Wildfires"}],
                    "sources": [{"url": "https://example.test/eonet"}],
                },
                "geometry": {"type": "Point", "coordinates": [7.01, 46.01]},
            }
        ]
    )

    result = NasaEonetPullStep(
        context_query(),
        service=FakeEonetService(response),
    ).run()

    assert result.provider_key == "nasa_eonet"
    assert result.count == 1
    assert result.events[0].provider == "NASA EONET"
    assert result.events[0].category == "Wildfires"


def test_usgs_step_processes_its_own_service_response():
    response = UsgsEarthquakeGeoJsonResponse(
        features=[
            {
                "id": "us7000abcd",
                "properties": {
                    "title": "M 4.5 - Switzerland",
                    "type": "earthquake",
                    "time": 1783000000000,
                    "status": "reviewed",
                    "mag": 4.5,
                    "url": "https://example.test/usgs",
                },
                "geometry": {"type": "Point", "coordinates": [7.2, 46.2, 10.0]},
            }
        ]
    )

    result = UsgsEarthquakePullStep(
        context_query(),
        service=FakeUsgsService(response),
    ).run()

    assert result.provider_key == "usgs_earthquakes"
    assert result.count == 1
    assert result.events[0].provider == "USGS Earthquake Catalog"
    assert result.events[0].magnitude == 4.5


def test_nasa_polygon_events_require_at_least_one_coordinate_inside_radius():
    inside = GeoCoordinate(latitude=46.01, longitude=7.01)
    outside = GeoCoordinate(latitude=48.0, longitude=7.0)
    feature = NasaEonetFeature(
        id="EONET_POLYGON",
        properties=NasaEonetProperties(id="EONET_POLYGON", title="Flood polygon"),
        geometry=GeoJsonPolygonGeometry(
            type="Polygon",
            coordinates=[[outside, inside]],
        ),
    )
    pull = NaturalEventsContextPull(
        context_query(),
        eonet=FakeEonetService(NasaEonetGeoJsonResponse(features=[feature])),
        usgs=FakeUsgsService(UsgsEarthquakeGeoJsonResponse(features=[])),
    )

    result = json.loads(pull.run())

    assert [event["id"] for event in result["events"]] == ["EONET_POLYGON"]
    assert result["events"][0]["latitude"] == pytest.approx(46.01)
    assert result["events"][0]["longitude"] == pytest.approx(7.01)


def test_nasa_event_without_usable_coordinates_returns_warning():
    feature = NasaEonetFeature(
        id="EONET_EMPTY",
        properties=NasaEonetProperties(id="EONET_EMPTY", title="Empty polygon"),
        geometry=GeoJsonPolygonGeometry(type="Polygon", coordinates=[]),
    )
    pull = NaturalEventsContextPull(
        context_query(),
        eonet=FakeEonetService(NasaEonetGeoJsonResponse(features=[feature])),
        usgs=FakeUsgsService(UsgsEarthquakeGeoJsonResponse(features=[])),
    )

    result = json.loads(pull.run())

    assert result["events"] == []
    assert result["warnings"] == [
        "NASA EONET returned an event without usable coordinates."
    ]


def test_partial_provider_failure_returns_partial_results():
    pull = NaturalEventsContextPull(
        context_query(),
        eonet=FailingEonetService(),
        usgs=FakeUsgsService(UsgsEarthquakeGeoJsonResponse(features=[])),
    )

    result = json.loads(pull.run())

    assert result["summary"]["counts"] == {
        "nasa_eonet": 0,
        "usgs_earthquakes": 0,
    }
    assert result["events"] == []
    assert result["warnings"] == ["NASA EONET could not be reached."]


def test_both_provider_failures_raise_unreachable_error():
    pull = NaturalEventsContextPull(
        context_query(),
        eonet=FailingEonetService(),
        usgs=FailingUsgsService(),
    )

    with pytest.raises(ValueError, match="Could not fetch natural events"):
        pull.run()


def test_both_malformed_provider_payloads_raise_malformed_error(monkeypatch):
    def fake_get(url, *, params, timeout):
        return FakeProviderResponse({"not_features": []})

    monkeypatch.setattr(natural_events_client_module.requests, "get", fake_get)
    pull = NaturalEventsContextPull(
        context_query(),
        eonet=NasaEonetService(),
        usgs=UsgsEarthquakeService(),
    )

    with pytest.raises(ValueError, match="malformed natural event data"):
        pull.run()


def test_final_json_excludes_none_fields():
    pull = NaturalEventsContextPull(
        context_query(),
        eonet=FakeEonetService(
            NasaEonetGeoJsonResponse(
                features=[
                    NasaEonetFeature(
                        id="EONET_1",
                        properties=NasaEonetProperties(id="EONET_1", title="Event"),
                        geometry=GeoJsonPointGeometry(
                            type="Point",
                            coordinates=GeoCoordinate(latitude=46.0, longitude=7.0),
                        ),
                    )
                ]
            )
        ),
        usgs=FakeUsgsService(UsgsEarthquakeGeoJsonResponse(features=[])),
    )

    result = json.loads(pull.run())

    assert "category" not in result["events"][0]
    assert "magnitude" not in result["events"][0]
    assert "source_url" not in result["events"][0]
    assert "warnings" not in result


class FakeEonetService:
    def __init__(self, response):
        self.response = response

    def build_geojson_query_params(self, query):
        return NasaEonetService(provider_limit=1).build_geojson_query_params(query)

    def get_events_geojson(self, params):
        return self.response


class FakeUsgsService:
    def __init__(self, response):
        self.response = response

    def build_geojson_query_params(self, query):
        return UsgsEarthquakeService(
            provider_limit=1,
            now_factory=fixed_now,
        ).build_geojson_query_params(query)

    def query_geojson(self, params):
        return self.response


class FailingEonetService(FakeEonetService):
    def __init__(self):
        super().__init__(NasaEonetGeoJsonResponse(features=[]))

    def get_events_geojson(self, params):
        raise requests.RequestException("timeout")


class FailingUsgsService(FakeUsgsService):
    def __init__(self):
        super().__init__(UsgsEarthquakeGeoJsonResponse(features=[]))

    def query_geojson(self, params):
        raise requests.RequestException("timeout")
