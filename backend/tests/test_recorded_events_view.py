import asyncio
import os
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import JSONB

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("OPENAI_API_URL", "http://test.local")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("MEDITRON_MCP_API_KEY", "test")
os.environ.setdefault("KEYCLOAK_API_ID", "test")
os.environ.setdefault("KEYCLOAK_API_SECRET", "test")

from api.models.recorded_event import ListRecordedEventsFilters, RecordedEvent
from api.services.recorded_events import RecordedEventService
from api.views.recorded_events import (
    count_recorded_events_by_country,
    list_recorded_events,
    router,
)
from tests.chat_room_helpers import make_recorded_event


class FakeRecordedEventService(RecordedEventService):
    def __init__(self, *, events=None, counts=None):
        self.events = events or []
        self.counts = counts or {}
        self.list_filters = None
        self.count_filters = None

    async def list_events(self, *, filters):
        self.list_filters = filters
        return self.events

    async def count_events_by_country(self, *, filters):
        self.count_filters = filters
        return self.counts


@pytest.mark.parametrize(
    "column_name",
    [
        "tags",
        "keywords",
        "affected_profession_categories",
        "response_profession_categories",
    ],
)
def test_filterable_recorded_event_metadata_uses_jsonb(column_name):
    assert isinstance(
        RecordedEvent.__table__.c[column_name].type,  # ty: ignore[unresolved-attribute]
        JSONB,
    )


def test_recorded_event_location_uses_indexed_relational_columns():
    table = RecordedEvent.__table__  # ty: ignore[unresolved-attribute]
    assert "event_location" not in table.c
    assert "location_granularity" not in table.c
    assert {
        "location_continent",
        "location_country_code",
        "location_latitude",
        "location_longitude",
    }.issubset(table.c.keys())
    assert {
        "ix_recordedevent_location_continent",
        "ix_recordedevent_location_country_code",
        "ix_recordedevent_location_latitude",
        "ix_recordedevent_location_longitude",
    }.issubset({index.name for index in table.indexes})


def test_recorded_event_end_dates_use_indexed_nullable_columns_and_range_constraint():
    table = RecordedEvent.__table__  # ty: ignore[unresolved-attribute]
    assert {
        "event_end_datetime",
        "event_end_date_granularity",
        "event_end_date_precision",
        "event_end_date_input",
    }.issubset(table.c.keys())
    assert table.c.event_end_datetime.nullable is True
    assert table.c.event_end_date_input.nullable is True
    assert {
        "ix_recordedevent_event_end_datetime",
        "ix_recordedevent_event_end_date_granularity",
        "ix_recordedevent_event_end_date_precision",
    }.issubset({index.name for index in table.indexes})
    assert "ck_recordedevent_event_date_range" in {
        constraint.name for constraint in table.constraints
    }


def test_list_recorded_events_returns_all_events_in_descending_order():
    older_event = make_recorded_event()
    newer_event = make_recorded_event(event_name="Newer event")
    newer_event.created_at = newer_event.created_at.replace(day=30)
    filters = ListRecordedEventsFilters()
    service = FakeRecordedEventService(events=[newer_event, older_event])

    response = asyncio.run(
        list_recorded_events(
            filters=filters,
            service=service,
        )
    )

    assert [event.id for event in response.events] == [newer_event.id, older_event.id]
    assert response.events[0].local_severity == 7.5
    assert response.events[0].country_severity == 4.0
    assert response.events[0].global_severity == 1.5
    assert service.list_filters is filters


def test_list_recorded_events_serializes_nested_location():
    event = make_recorded_event(
        event_location={
            "raw_text": "Geneva, Switzerland",
            "continent": "europe",
            "country_code": "CH",
            "region": "Geneva",
            "city": "Geneva",
            "address": None,
            "place_name": None,
            "detail": None,
            "coordinates": None,
        }
    )
    response = asyncio.run(
        list_recorded_events(
            filters=ListRecordedEventsFilters(),
            service=FakeRecordedEventService(events=[event]),
        )
    )

    assert response.events[0].event_location.model_dump(mode="json") == {
        "raw_text": "Geneva, Switzerland",
        "continent": "europe",
        "country_code": "CH",
        "region": "Geneva",
        "city": "Geneva",
        "address": None,
        "place_name": None,
        "detail": None,
        "coordinates": None,
    }


def test_list_recorded_events_serializes_optional_event_end_date():
    event = make_recorded_event(
        event_end_datetime=datetime(2026, 6, 28, 23, 59, tzinfo=UTC)
    )

    response = asyncio.run(
        list_recorded_events(
            filters=ListRecordedEventsFilters(),
            service=FakeRecordedEventService(events=[event]),
        )
    )

    [serialized_event] = response.events
    assert serialized_event.event_end_datetime == datetime(
        2026, 6, 28, 23, 59, tzinfo=UTC
    )
    assert serialized_event.event_end_date_granularity == "day"
    assert serialized_event.event_end_date_precision == "exact"
    assert serialized_event.event_end_date_input is not None


def test_recorded_event_filters_are_exposed_as_repeated_query_parameters():
    app = FastAPI()
    app.include_router(router)

    for path in ["/recorded-events", "/recorded-events/count-by-country"]:
        parameters = app.openapi()["paths"][path]["get"]["parameters"]
        parameters_by_name = {parameter["name"]: parameter for parameter in parameters}

        assert parameters_by_name["keyword"]["in"] == "query"
        for parameter_name in [
            "tags",
            "affected_profession_categories",
            "response_profession_categories",
        ]:
            assert parameters_by_name[parameter_name]["in"] == "query"
            schema = parameters_by_name[parameter_name]["schema"]
            assert any(option.get("type") == "array" for option in schema["anyOf"])


def test_count_recorded_events_by_country_serializes_service_counts():
    filters = ListRecordedEventsFilters()
    service = FakeRecordedEventService(counts={"CH": 2, "UNKNOWN": 1})

    response = asyncio.run(
        count_recorded_events_by_country(
            filters=filters,
            service=service,
        )
    )

    assert {
        country_code: count.model_dump() for country_code, count in response.items()
    } == {
        "CH": {"event_count": 2},
        "UNKNOWN": {"event_count": 1},
    }
    assert service.count_filters is filters


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("tags", ["unknown_tag"]),
        ("affected_profession_categories", ["unknown_profession"]),
        ("response_profession_categories", ["unknown_profession"]),
    ],
)
def test_recorded_event_filters_reject_unknown_fixed_values(field_name, value):
    with pytest.raises(ValidationError):
        ListRecordedEventsFilters.model_validate({field_name: value})


@pytest.mark.parametrize("keyword", ["", "   "])
def test_recorded_event_filters_reject_empty_keywords(keyword):
    with pytest.raises(ValidationError):
        ListRecordedEventsFilters(keyword=keyword)
