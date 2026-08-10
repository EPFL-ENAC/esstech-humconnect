from typing import Any, cast

from tests.chat_room_helpers import *  # noqa: F403


def dashboard_filters():
    return recorded_events_module.ListRecordedEventsFilters(
        keyword=" medical ",
        tags=["supply_shortage", "equipment_issue"],
        affected_profession_categories=["medical_clinical", "community_health"],
        response_profession_categories=[
            "logistics_supply",
            "biomedical_equipment",
        ],
    )


def assert_dashboard_filter_query(query_text):
    assert "CAST(recordedevent.keywords AS TEXT)" in query_text
    assert "lower(recordedevent.event_name)" not in query_text
    assert query_text.count("recordedevent.tags @>") == 2
    assert query_text.count("recordedevent.affected_profession_categories @>") == 2
    assert query_text.count("recordedevent.response_profession_categories @>") == 2
    assert " AS JSONB)" not in query_text
    assert query_text.count(" OR ") == 3
    assert query_text.count(" AND ") >= 3


def test_recorded_event_service_lists_events_in_descending_order():
    FakeAsyncSession.reset()
    older_event = make_recorded_event()
    newer_event = make_recorded_event(event_name="Newer event")
    newer_event.created_at = newer_event.created_at.replace(day=30)
    FakeAsyncSession.rows[RecordedEvent][older_event.id] = older_event
    FakeAsyncSession.rows[RecordedEvent][newer_event.id] = newer_event
    service = recorded_events_module.RecordedEventService(
        session_factory=cast(Any, FakeAsyncSession),
        engine_factory=cast(Any, lambda: object()),
    )

    events = asyncio.run(
        service.list_events(filters=recorded_events_module.ListRecordedEventsFilters())
    )

    assert events == [newer_event, older_event]
    query_text = str(FakeAsyncSession.last_query)
    assert "ORDER BY recordedevent.created_at DESC" in query_text
    assert "WHERE" not in query_text


def test_recorded_event_service_applies_dashboard_filters_to_list_query():
    FakeAsyncSession.reset()
    filters = dashboard_filters()
    service = recorded_events_module.RecordedEventService(
        session_factory=cast(Any, FakeAsyncSession),
        engine_factory=cast(Any, lambda: object()),
    )

    asyncio.run(service.list_events(filters=filters))

    assert filters.keyword == "medical"
    query_text = str(FakeAsyncSession.last_query)
    assert_dashboard_filter_query(query_text)
    assert "ORDER BY recordedevent.created_at DESC" in query_text


def test_recorded_event_service_counts_events_by_country():
    FakeAsyncSession.reset()
    swiss_event = make_recorded_event(
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
    other_swiss_event = make_recorded_event(event_name="Another Swiss event")
    other_swiss_event.location_country_code = "CH"
    unknown_event = make_recorded_event(event_name="Unplaced event")
    for event in [swiss_event, other_swiss_event, unknown_event]:
        FakeAsyncSession.rows[RecordedEvent][event.id] = event
    service = recorded_events_module.RecordedEventService(
        session_factory=cast(Any, FakeAsyncSession),
        engine_factory=cast(Any, lambda: object()),
    )

    counts = asyncio.run(
        service.count_events_by_country(
            filters=recorded_events_module.ListRecordedEventsFilters()
        )
    )

    assert counts == {"CH": 2, "UNKNOWN": 1}
    query_text = str(FakeAsyncSession.last_query)
    assert "coalesce(recordedevent.location_country_code" in query_text
    assert "count(recordedevent.id)" in query_text
    assert "GROUP BY coalesce(recordedevent.location_country_code" in query_text


def test_recorded_event_service_applies_dashboard_filters_to_country_count_query():
    FakeAsyncSession.reset()
    filters = dashboard_filters()
    service = recorded_events_module.RecordedEventService(
        session_factory=cast(Any, FakeAsyncSession),
        engine_factory=cast(Any, lambda: object()),
    )

    counts = asyncio.run(service.count_events_by_country(filters=filters))

    assert counts == {}
    assert filters.keyword == "medical"
    assert_dashboard_filter_query(str(FakeAsyncSession.last_query))


def test_recorded_event_service_persists_event_with_initiator_metadata():
    FakeAsyncSession.reset()
    event_input = events_tool_module.RecordEventToolInput.model_validate(
        structured_record_event_arguments()
    )
    service = recorded_events_module.RecordedEventService(
        session_factory=cast(Any, FakeAsyncSession),
        engine_factory=cast(Any, lambda: object()),
        now_factory=lambda: datetime(2026, 6, 29, 12, 0, tzinfo=UTC),
    )

    async def run():
        return await service.record_event_from_tool(
            event_input=event_input,
            chat_id=RECORDED_EVENT_CHAT_ID,
            user_id=TEST_USER_ID,
            source_message_id=RECORDED_EVENT_SOURCE_MESSAGE_ID,
        )

    response = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.chat_id == RECORDED_EVENT_CHAT_ID
    assert persisted_event.initiated_by_user_id == TEST_USER_ID
    assert persisted_event.source_message_id == RECORDED_EVENT_SOURCE_MESSAGE_ID
    assert persisted_event.original_text == "My son started coughing 3 days ago"
    assert persisted_event.event_name == "Son started coughing"
    assert persisted_event.event_datetime == datetime(2026, 6, 26, 0, 0, tzinfo=UTC)
    assert persisted_event.event_date_granularity == "day"
    assert persisted_event.event_date_precision == "exact"
    assert persisted_event.event_date_input == {
        "year": None,
        "month": None,
        "day_selection": {
            "mode": "day",
            "day": {"kind": "relative", "value": -3},
        },
        "hour": None,
        "minute": None,
        "precision": "exact",
        "timezone": None,
    }
    assert persisted_event.event_end_datetime is None
    assert persisted_event.event_end_date_granularity is None
    assert persisted_event.event_end_date_precision is None
    assert persisted_event.event_end_date_input is None
    assert persisted_event.event_location().model_dump(mode="json") == {
        "raw_text": None,
        "continent": None,
        "country_code": None,
        "region": None,
        "city": None,
        "address": None,
        "place_name": None,
        "detail": None,
        "coordinates": None,
    }
    assert persisted_event.tags == ["health_incident"]
    assert persisted_event.keywords == ["symptom", "cough"]
    assert persisted_event.affected_profession_categories == ["medical_clinical"]
    assert persisted_event.response_profession_categories == ["medical_clinical"]
    assert persisted_event.local_severity == 7.5
    assert persisted_event.country_severity == 4.0
    assert persisted_event.global_severity == 1.5
    assert response == persisted_event


def test_recorded_event_service_builds_user_scoped_filtered_recall_query():
    FakeAsyncSession.reset()
    cough_event = make_recorded_event()
    other_chat_event = make_recorded_event(
        chat_id=uuid4(),
        created_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
    )
    FakeAsyncSession.rows[RecordedEvent][cough_event.id] = cough_event
    FakeAsyncSession.rows[RecordedEvent][other_chat_event.id] = other_chat_event

    recall_input = events_tool_module.RecallEventsToolInput.model_validate(
        {
            "keyword": "cough",
            "date_start": "2026-06-20T00:00:00+00:00",
            "date_end": "2026-06-30T00:00:00+00:00",
            "tags": ["health_incident"],
            "tag_match": "all",
            "limit": 10,
        }
    )
    service = recorded_events_module.RecordedEventService(
        session_factory=cast(Any, FakeAsyncSession),
        engine_factory=cast(Any, lambda: object()),
    )

    async def run():
        return await service.recall_events_from_tool(
            recall_input=recall_input,
            user_id=TEST_USER_ID,
        )

    assert asyncio.run(run()) == [other_chat_event, cough_event]

    query_text = str(FakeAsyncSession.last_query)
    assert "recordedevent.initiated_by_user_id" in query_text
    assert "WHERE recordedevent.chat_id" not in query_text
    assert "AND recordedevent.chat_id" not in query_text
    assert (
        "coalesce(recordedevent.event_end_datetime, "
        "recordedevent.event_datetime) >= " in query_text
    )
    assert (
        "coalesce(recordedevent.event_datetime, "
        "recordedevent.event_end_datetime) <= " in query_text
    )
    assert "lower(recordedevent.event_name) LIKE lower(" in query_text
    assert "lower(recordedevent.original_text) LIKE lower(" in query_text
    assert "lower(recordedevent.location_raw_text) LIKE lower(" in query_text
    assert "lower(recordedevent.location_country_code) LIKE lower(" in query_text
    assert "event_location" not in query_text
    assert "CAST(recordedevent.keywords AS TEXT)" in query_text
    assert "recordedevent.tags @>" in query_text
    assert "CAST(recordedevent.tags AS JSONB)" not in query_text
    assert "CAST(recordedevent.tags AS VARCHAR)" not in query_text
    assert " LIMIT " in query_text


@pytest.mark.parametrize(
    ("tag_match", "expected_join"),
    [("all", " AND "), ("any", " OR ")],
)
def test_recorded_event_service_combines_exact_tag_filters(
    tag_match,
    expected_join,
):
    FakeAsyncSession.reset()
    recall_input = events_tool_module.RecallEventsToolInput.model_validate(
        {
            "keyword": None,
            "date_start": None,
            "date_end": None,
            "tags": ["supply_shortage", "equipment_issue"],
            "tag_match": tag_match,
            "limit": 10,
        }
    )
    service = recorded_events_module.RecordedEventService(
        session_factory=cast(Any, FakeAsyncSession),
        engine_factory=cast(Any, lambda: object()),
    )

    async def run():
        return await service.recall_events_from_tool(
            recall_input=recall_input,
            user_id=TEST_USER_ID,
        )

    asyncio.run(run())
    query_text = str(FakeAsyncSession.last_query)
    assert query_text.count("recordedevent.tags @>") == 2
    assert "CAST(recordedevent.tags AS JSONB)" not in query_text
    assert expected_join in query_text
    assert "CAST(recordedevent.tags AS VARCHAR)" not in query_text
