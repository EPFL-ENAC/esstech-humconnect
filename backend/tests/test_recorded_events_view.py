import asyncio
import os

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
from api.views.recorded_events import list_recorded_events, router
from tests.chat_room_helpers import FakeAsyncSession, make_recorded_event


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
    assert isinstance(RecordedEvent.__table__.c[column_name].type, JSONB)


def test_recorded_event_location_uses_indexed_relational_columns():
    table = RecordedEvent.__table__
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


def test_list_recorded_events_returns_all_events_in_descending_order():
    FakeAsyncSession.reset()
    older_event = make_recorded_event()
    newer_event = make_recorded_event(event_name="Newer event")
    newer_event.created_at = newer_event.created_at.replace(day=30)
    FakeAsyncSession.rows[RecordedEvent][older_event.id] = older_event
    FakeAsyncSession.rows[RecordedEvent][newer_event.id] = newer_event
    session = FakeAsyncSession()

    response = asyncio.run(
        list_recorded_events(
            filters=ListRecordedEventsFilters(),
            user=object(),
            session=session,
        )
    )

    assert [event.id for event in response.events] == [newer_event.id, older_event.id]
    assert response.events[0].local_severity == 7.5
    assert response.events[0].country_severity == 4.0
    assert response.events[0].global_severity == 1.5
    query_text = str(FakeAsyncSession.last_query)
    assert "ORDER BY recordedevent.created_at DESC" in query_text
    assert "WHERE" not in query_text


def test_list_recorded_events_serializes_nested_location():
    FakeAsyncSession.reset()
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
    FakeAsyncSession.rows[RecordedEvent][event.id] = event

    response = asyncio.run(
        list_recorded_events(
            filters=ListRecordedEventsFilters(),
            user=object(),
            session=FakeAsyncSession(),
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


def test_recorded_event_filters_are_exposed_as_repeated_query_parameters():
    app = FastAPI()
    app.include_router(router)

    parameters = app.openapi()["paths"]["/recorded-events"]["get"]["parameters"]
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


def test_list_recorded_events_combines_filter_groups_with_exact_any_matching():
    FakeAsyncSession.reset()
    session = FakeAsyncSession()
    filters = ListRecordedEventsFilters(
        keyword=" medical ",
        tags=["supply_shortage", "equipment_issue"],
        affected_profession_categories=["medical_clinical", "community_health"],
        response_profession_categories=["logistics_supply", "biomedical_equipment"],
    )

    asyncio.run(
        list_recorded_events(
            filters=filters,
            user=object(),
            session=session,
        )
    )

    assert filters.keyword == "medical"
    query_text = str(FakeAsyncSession.last_query)
    assert "CAST(recordedevent.keywords AS TEXT)" in query_text
    assert "lower(recordedevent.event_name)" not in query_text
    assert query_text.count("recordedevent.tags @>") == 2
    assert query_text.count("recordedevent.affected_profession_categories @>") == 2
    assert query_text.count("recordedevent.response_profession_categories @>") == 2
    assert " AS JSONB)" not in query_text
    assert query_text.count(" OR ") == 3
    assert query_text.count(" AND ") >= 3
    assert "ORDER BY recordedevent.created_at DESC" in query_text


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
