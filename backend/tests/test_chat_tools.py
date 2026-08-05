from tests.chat_room_helpers import *  # noqa: F403


def test_ask_meditron_tool_calls_meditron_with_prompt(monkeypatch):
    calls = []

    class FakeMeditronResponse:
        def __init__(self, text):
            self.output_text = text

    async def fake_meditron_create(*, model, instructions, input):
        calls.append((instructions, input))
        return FakeMeditronResponse("Meditron answer")

    monkeypatch.setattr(
        meditron_tool_module.openai_client.responses,
        "create",
        fake_meditron_create,
    )

    async def run():
        return await ASK_MEDITRON_TOOL.execute(
            {"prompt": "What is cholera?", "system_prompt": ""}
        )

    assert asyncio.run(run()) == "Meditron answer"
    assert calls == [("", "What is cholera?")]


def test_ask_meditron_tool_passes_system_prompt(monkeypatch):
    calls = []

    class FakeMeditronResponse:
        def __init__(self, text):
            self.output_text = text

    async def fake_meditron_create(*, model, instructions, input):
        calls.append((instructions, input))
        return FakeMeditronResponse("Clinical answer")

    monkeypatch.setattr(
        meditron_tool_module.openai_client.responses,
        "create",
        fake_meditron_create,
    )

    async def run():
        return await ASK_MEDITRON_TOOL.execute(
            {
                "prompt": "How should dehydration be assessed?",
                "system_prompt": "Answer concisely.",
            }
        )

    assert asyncio.run(run()) == "Clinical answer"
    assert calls == [("Answer concisely.", "How should dehydration be assessed?")]


@pytest.mark.parametrize("prompt", ["", 123, None])
def test_ask_meditron_tool_rejects_missing_or_empty_prompt(prompt):
    async def run():
        return await ASK_MEDITRON_TOOL.execute({"prompt": prompt})

    with pytest.raises(ValueError, match="invalid query data"):
        asyncio.run(run())


def test_ask_meditron_tool_rejects_non_string_system_prompt():
    async def run():
        return await ASK_MEDITRON_TOOL.execute(
            {"prompt": "What is cholera?", "system_prompt": 42}
        )

    with pytest.raises(ValueError, match="invalid query data"):
        asyncio.run(run())


@pytest.mark.parametrize(
    "arguments",
    [
        {"center_latitude": -91.0, "center_longitude": 7.0, "radius_km": 10.0},
        {"center_latitude": 46.0, "center_longitude": 181.0, "radius_km": 10.0},
        {"center_latitude": 46.0, "center_longitude": 7.0, "radius_km": 0.0},
        {"center_latitude": 46.0, "center_longitude": 7.0, "radius_km": -1.0},
        {"center_latitude": 46.0, "center_longitude": 7.0, "radius_km": 1000.1},
    ],
)
def test_get_natural_events_context_tool_rejects_invalid_input(arguments):
    async def run():
        return await GET_NATURAL_EVENTS_CONTEXT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid query data"):
        asyncio.run(run())


def test_get_natural_events_context_tool_delegates_to_pull(monkeypatch):
    calls = []

    class FakeNaturalEventsContextPull:
        def __init__(self, query):
            calls.append(query)

        def run(self):
            return json.dumps(
                {
                    "summary": {
                        "message": "Found 0 natural event(s) near the requested area.",
                        "counts": {
                            "nasa_eonet": 0,
                            "usgs_earthquakes": 0,
                        },
                    },
                    "center": {
                        "latitude": 46.0,
                        "longitude": 7.0,
                        "radius_km": 100.0,
                    },
                    "events": [],
                }
            )

    monkeypatch.setattr(
        natural_events_tool_module,
        "NaturalEventsContextPull",
        FakeNaturalEventsContextPull,
    )

    async def run():
        return await GET_NATURAL_EVENTS_CONTEXT_TOOL.execute(
            {
                "center_latitude": 46.0,
                "center_longitude": 7.0,
                "radius_km": 100.0,
            }
        )

    result = json.loads(asyncio.run(run()))

    assert len(calls) == 1
    assert calls[0].center_latitude == 46.0
    assert calls[0].center_longitude == 7.0
    assert calls[0].radius_km == 100.0
    assert result["summary"]["counts"] == {
        "nasa_eonet": 0,
        "usgs_earthquakes": 0,
    }


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"country_name": ""},
        {"country_name": "   "},
        {"country_name": 123},
    ],
)
def test_get_humanitarian_context_tool_rejects_invalid_input(arguments):
    async def run():
        return await GET_HUMANITARIAN_CONTEXT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid query data"):
        asyncio.run(run())


def test_get_humanitarian_context_tool_fetches_and_normalizes_items(monkeypatch):
    calls = []

    def fake_post(url, *, params, json, timeout):
        calls.append((url, params, json, timeout))
        if url.endswith("/reports"):
            return FakeReliefWebResponse(
                {
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

        return FakeReliefWebResponse(
            {
                "data": [
                    {
                        "id": "dis-1",
                        "fields": {
                            "name": "Haiti: Floods - Jul 2026",
                            "url": "https://example.test/disaster",
                            "date": {"created": "2026-07-01T10:00:00+00:00"},
                            "primary_country": {"name": "Haiti"},
                            "type": [{"name": "Flood"}],
                        },
                    }
                ]
            }
        )

    monkeypatch.setattr(reliefweb_client_module.requests, "post", fake_post)

    async def run():
        return await GET_HUMANITARIAN_CONTEXT_TOOL.execute({"country_name": " Haiti "})

    result = json.loads(asyncio.run(run()))

    assert result["summary"]["counts"] == {
        "reports": 1,
        "disasters": 1,
    }
    assert result["country"] == "Haiti"
    assert {
        key: value for key, value in result["filters"].items() if key != "created_from"
    } == {
        "provider": "ReliefWeb",
        "country": "Haiti",
        "limit_per_endpoint": 10,
        "sort": ["date.created:desc"],
        "report_query": reliefweb_client_module.HUMANITARIAN_CONTEXT_QUERY,
        "disaster_status": "current",
    }
    assert [item["id"] for item in result["items"]] == ["123", "dis-1"]
    assert result["items"][0] == {
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
    assert result["items"][1] == {
        "provider": "ReliefWeb",
        "type": "disaster",
        "id": "dis-1",
        "title": "Haiti: Floods - Jul 2026",
        "category": "Flood",
        "time": "2026-07-01T10:00:00Z",
        "source_url": "https://example.test/disaster",
        "sources": [],
        "country": "Haiti",
        "location_precision": "country",
    }

    report_url, report_params, report_payload, report_timeout = calls[0]
    assert report_url.endswith("/reports")
    assert report_params == {
        "appname": reliefweb_client_module.config.RELIEFWEB_APP_NAME
    }
    assert report_payload["limit"] == 10
    assert report_payload["sort"] == ["date.created:desc"]
    assert report_payload["query"]["value"].startswith("outbreak epidemic")
    assert report_payload["fields"]["include"] == [
        "id",
        "title",
        "url",
        "date",
        "primary_country",
        "source",
        "disaster",
        "disaster_type",
        "theme",
        "format",
    ]
    assert {
        condition["field"]: condition["value"]
        for condition in report_payload["filter"]["conditions"]
    }["primary_country.name"] == "Haiti"
    report_date_from = {
        condition["field"]: condition["value"]
        for condition in report_payload["filter"]["conditions"]
    }["date.created"]["from"]
    assert "T" in report_date_from
    assert report_date_from.endswith("+00:00")
    assert result["filters"]["created_from"] == report_date_from
    assert report_timeout == 5

    disaster_url, disaster_params, disaster_payload, disaster_timeout = calls[1]
    assert disaster_url.endswith("/disasters")
    assert disaster_params == {
        "appname": reliefweb_client_module.config.RELIEFWEB_APP_NAME
    }
    assert "query" not in disaster_payload
    assert disaster_payload["fields"]["include"] == [
        "id",
        "name",
        "url",
        "date",
        "primary_country",
        "type",
        "status",
    ]
    assert {
        condition["field"]: condition["value"]
        for condition in disaster_payload["filter"]["conditions"]
    }["status"] == "current"
    disaster_date_from = {
        condition["field"]: condition["value"]
        for condition in disaster_payload["filter"]["conditions"]
    }["date.created"]["from"]
    assert "T" in disaster_date_from
    assert disaster_date_from.endswith("+00:00")
    assert disaster_date_from == report_date_from
    assert disaster_timeout == 5


def test_get_humanitarian_context_tool_returns_partial_results(monkeypatch):
    def fake_post(url, *, params, json, timeout):
        if url.endswith("/reports"):
            raise reliefweb_client_module.requests.RequestException("timeout")

        return FakeReliefWebResponse({"data": []})

    monkeypatch.setattr(reliefweb_client_module.requests, "post", fake_post)

    async def run():
        return await GET_HUMANITARIAN_CONTEXT_TOOL.execute({"country_name": "Sudan"})

    result = json.loads(asyncio.run(run()))

    assert result["summary"]["counts"] == {
        "reports": 0,
        "disasters": 0,
    }
    assert result["country"] == "Sudan"
    assert result["items"] == []
    assert result["warnings"] == ["ReliefWeb reports could not be reached."]


def test_get_humanitarian_context_tool_rejects_all_reliefweb_failures(monkeypatch):
    def fake_post(url, *, params, json, timeout):
        raise reliefweb_client_module.requests.RequestException("timeout")

    monkeypatch.setattr(reliefweb_client_module.requests, "post", fake_post)

    async def run():
        return await GET_HUMANITARIAN_CONTEXT_TOOL.execute({"country_name": "Sudan"})

    with pytest.raises(ValueError, match="humanitarian context from ReliefWeb"):
        asyncio.run(run())


def test_get_humanitarian_context_tool_rejects_all_malformed_payloads(monkeypatch):
    def fake_post(url, *, params, json, timeout):
        return FakeReliefWebResponse({"not_data": []})

    monkeypatch.setattr(reliefweb_client_module.requests, "post", fake_post)

    async def run():
        return await GET_HUMANITARIAN_CONTEXT_TOOL.execute({"country_name": "Sudan"})

    with pytest.raises(ValueError, match="malformed humanitarian context data"):
        asyncio.run(run())


def test_record_event_tool_delegates_to_recorded_event_service(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)

    async def run():
        return await RECORD_EVENT_TOOL.execute(
            structured_record_event_arguments(),
            record_event_tool_context(),
        )

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.chat_id == RECORDED_EVENT_CHAT_ID
    assert persisted_event.initiated_by_user_id == TEST_USER_ID
    assert persisted_event.source_message_id == RECORDED_EVENT_SOURCE_MESSAGE_ID
    assert output == expected_record_event_tool_output(persisted_event)


def test_recall_events_tool_delegates_to_recorded_event_service(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    cough_event = make_recorded_event()
    fever_event = make_recorded_event(
        original_text="My son had a fever yesterday",
        event_name="Son had fever",
        event_datetime=datetime(2026, 6, 28, 12, 0, tzinfo=UTC),
        keywords=["symptom", "fever"],
        created_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
    )
    FakeAsyncSession.rows[RecordedEvent][cough_event.id] = cough_event
    FakeAsyncSession.rows[RecordedEvent][fever_event.id] = fever_event

    arguments = {
        "keyword": "son",
        "date_start": "2026-06-20T00:00:00+00:00",
        "date_end": "2026-06-30T00:00:00+00:00",
        "tags": ["health_incident"],
        "tag_match": "any",
        "limit": 5,
    }

    async def run():
        return await RECALL_EVENTS_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    assert output == expected_recall_events_tool_output([fever_event, cough_event])


def test_recall_events_tool_requires_execution_context(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    cough_event = make_recorded_event()
    FakeAsyncSession.rows[RecordedEvent][cough_event.id] = cough_event

    async def run():
        return await RECALL_EVENTS_TOOL.execute(
            {
                "keyword": "cough",
                "date_start": None,
                "date_end": None,
                "tags": [],
                "tag_match": "all",
                "limit": 10,
            }
        )

    with pytest.raises(ValueError, match="requires chat execution context"):
        asyncio.run(run())


def test_recall_events_tool_rejects_invalid_date_range():
    async def run():
        return await RECALL_EVENTS_TOOL.execute(
            {
                "keyword": None,
                "date_start": "2026-06-30T00:00:00+00:00",
                "date_end": "2026-06-20T00:00:00+00:00",
                "tags": [],
                "tag_match": "all",
                "limit": 10,
            },
            record_event_tool_context(),
        )

    with pytest.raises(ValueError, match="invalid query data"):
        asyncio.run(run())


def test_record_event_tool_schema_exposes_component_date_shape():
    parameters = RECORD_EVENT_TOOL.definition["parameters"]
    defs = parameters["$defs"]
    event_date_schema = defs["RecordEventDateInput"]
    day_selection_schema = defs["RecordEventDaySelectionInput"]
    week_selection_schema = defs["RecordEventWeekSelectionInput"]
    temporal_entry_schema = defs["RecordEventTemporalEntryInput"]
    relative_entry_schema = defs["RecordEventRelativeTemporalEntryInput"]
    location_schema = defs["RecordEventLocationInput"]
    coordinates_schema = defs["EventCoordinates"]
    severity_schema = parameters["properties"]["severity"]

    assert RECORD_EVENT_TOOL.definition["type"] == "function"
    assert RECORD_EVENT_TOOL.definition["strict"] is True
    assert parameters["additionalProperties"] is False
    assert event_date_schema["additionalProperties"] is False
    assert day_selection_schema["additionalProperties"] is False
    assert week_selection_schema["additionalProperties"] is False
    assert temporal_entry_schema["additionalProperties"] is False
    assert relative_entry_schema["additionalProperties"] is False
    assert location_schema["additionalProperties"] is False
    assert parameters["properties"]["event_date"] == {
        "$ref": "#/$defs/RecordEventDateInput"
    }
    assert any(
        option.get("$ref") == "#/$defs/RecordEventDateInput"
        for option in parameters["properties"]["event_end_date"]["anyOf"]
    )
    assert any(
        option.get("type") == "null"
        for option in parameters["properties"]["event_end_date"]["anyOf"]
    )
    assert event_date_schema["required"] == [
        "year",
        "month",
        "day_selection",
        "hour",
        "minute",
        "precision",
        "timezone",
    ]
    assert temporal_entry_schema["required"] == ["kind", "value"]
    assert relative_entry_schema["required"] == ["kind", "value"]
    assert parameters["properties"]["original_text"]["description"] == (
        "The exact user text that contains the event."
    )
    assert parameters["properties"]["tags"]["items"]["enum"] == list(EVENT_TAGS)
    assert parameters["properties"]["tags"]["minItems"] == 1
    assert parameters["properties"]["affected_profession_categories"]["items"][
        "enum"
    ] == list(PROFESSION_CATEGORIES)
    assert parameters["properties"]["response_profession_categories"]["items"][
        "enum"
    ] == list(PROFESSION_CATEGORIES)
    assert parameters["properties"]["event_location"] == {
        "$ref": "#/$defs/RecordEventLocationInput"
    }
    assert location_schema["required"] == [
        "raw_text",
        "continent",
        "country_code",
        "region",
        "city",
        "address",
        "place_name",
        "detail",
        "coordinates",
    ]
    assert location_schema["properties"]["continent"]["anyOf"][0]["enum"] == list(
        EVENT_CONTINENTS
    )
    assert (
        location_schema["properties"]["country_code"]["anyOf"][0]["pattern"]
        == "^[A-Z]{2}$"
    )
    assert coordinates_schema["properties"]["latitude"]["minimum"] == -90
    assert coordinates_schema["properties"]["latitude"]["maximum"] == 90
    assert coordinates_schema["properties"]["longitude"]["minimum"] == -180
    assert coordinates_schema["properties"]["longitude"]["maximum"] == 180
    assert severity_schema["additionalProperties"] is False
    assert severity_schema["required"] == ["local", "country", "global"]
    for scale in ["local", "country", "global"]:
        assert severity_schema["properties"][scale]["minimum"] == 0
        assert severity_schema["properties"][scale]["maximum"] == 10
    assert parameters["required"] == [
        "original_text",
        "event_name",
        "event_date",
        "event_end_date",
        "event_location",
        "tags",
        "keywords",
        "affected_profession_categories",
        "response_profession_categories",
        "severity",
    ]
    assert temporal_entry_schema["properties"]["kind"]["enum"] == [
        "absolute",
        "relative",
    ]
    assert relative_entry_schema["properties"]["kind"]["const"] == "relative"
    assert temporal_entry_schema["properties"]["value"]["type"] == "integer"
    day_or_week_schema = event_date_schema["properties"]["day_selection"]["anyOf"][0]
    assert day_or_week_schema["discriminator"] == {
        "mapping": {
            "day": "#/$defs/RecordEventDaySelectionInput",
            "week": "#/$defs/RecordEventWeekSelectionInput",
        },
        "propertyName": "mode",
    }
    assert day_or_week_schema["oneOf"] == [
        {"$ref": "#/$defs/RecordEventDaySelectionInput"},
        {"$ref": "#/$defs/RecordEventWeekSelectionInput"},
    ]
    assert day_selection_schema["required"] == ["mode", "day"]
    assert week_selection_schema["required"] == ["mode", "week", "weekday"]
    weekday_schema = week_selection_schema["properties"]["weekday"]["anyOf"][0]
    assert weekday_schema["minimum"] == 1
    assert weekday_schema["maximum"] == 7
    assert event_date_schema["properties"]["timezone"]["description"].startswith(
        "An IANA timezone"
    )


def test_record_event_tool_accepts_json_stringified_structured_fields(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_end_date"] = component_event_date_arguments(
        day_selection={
            "mode": "day",
            "day": {"kind": "relative", "value": -1},
        }
    )
    arguments["event_date"] = json.dumps(arguments["event_date"])
    arguments["event_end_date"] = json.dumps(arguments["event_end_date"])
    arguments["event_location"] = json.dumps(arguments["event_location"])
    arguments["tags"] = json.dumps(arguments["tags"])
    arguments["keywords"] = json.dumps(arguments["keywords"])
    arguments["affected_profession_categories"] = json.dumps(
        arguments["affected_profession_categories"]
    )
    arguments["response_profession_categories"] = json.dumps(
        arguments["response_profession_categories"]
    )
    arguments["severity"] = json.dumps(arguments["severity"])

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 26, 0, 0, tzinfo=UTC)
    assert persisted_event.event_end_datetime == datetime(
        2026, 6, 28, 23, 59, 59, 999999, tzinfo=UTC
    )
    assert persisted_event.tags == ["health_incident"]
    assert persisted_event.keywords == ["symptom", "cough"]
    assert persisted_event.affected_profession_categories == ["medical_clinical"]
    assert persisted_event.response_profession_categories == ["medical_clinical"]
    assert persisted_event.local_severity == 7.5
    assert persisted_event.country_severity == 4.0
    assert persisted_event.global_severity == 1.5
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_persists_structured_location(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_location"] = {
        "raw_text": "the river near the bridge in Geneva",
        "continent": "europe",
        "country_code": "CH",
        "region": "Geneva",
        "city": "Geneva",
        "address": None,
        "place_name": "the river",
        "detail": "near the bridge",
        "coordinates": {"latitude": 46.2044, "longitude": 6.1432},
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.location_continent == "europe"
    assert persisted_event.location_country_code == "CH"
    assert persisted_event.location_city == "Geneva"
    assert persisted_event.location_latitude == 46.2044
    assert persisted_event.location_longitude == 6.1432
    assert '"country_code": "CH"' in output


@pytest.mark.parametrize(
    "location",
    [
        {
            "raw_text": "Paris",
            "continent": "europe",
            "country_code": "fr",
            "region": None,
            "city": "Paris",
            "address": None,
            "place_name": None,
            "detail": None,
            "coordinates": None,
        },
        {
            "raw_text": "Unknown country",
            "continent": None,
            "country_code": "ZZ",
            "region": None,
            "city": None,
            "address": None,
            "place_name": None,
            "detail": None,
            "coordinates": None,
        },
        {
            "raw_text": "coordinates",
            "continent": None,
            "country_code": None,
            "region": None,
            "city": None,
            "address": None,
            "place_name": None,
            "detail": None,
            "coordinates": {"latitude": 91, "longitude": 0},
        },
        {
            "raw_text": "coordinates",
            "continent": None,
            "country_code": None,
            "region": None,
            "city": None,
            "address": None,
            "place_name": None,
            "detail": None,
            "coordinates": {"latitude": 46},
        },
    ],
)
def test_record_event_tool_rejects_invalid_structured_location(location):
    arguments = structured_record_event_arguments()
    arguments["event_location"] = location

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid event data"):
        asyncio.run(run())


@pytest.mark.parametrize(
    "severity",
    [
        {"local": -0.1, "country": 5, "global": 5},
        {"local": 5, "country": 10.1, "global": 5},
        {"local": 5, "country": 5, "global": 11},
        {"local": "high", "country": 5, "global": 5},
        {"local": 5, "country": 5},
    ],
)
def test_record_event_tool_rejects_invalid_severity(severity):
    arguments = structured_record_event_arguments()
    arguments["severity"] = severity

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid event data"):
        asyncio.run(run())


def test_record_event_tool_requires_severity():
    arguments = structured_record_event_arguments()
    del arguments["severity"]

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid event data"):
        asyncio.run(run())


def test_record_event_tool_requires_execution_context(monkeypatch):
    configure_recorded_event_service(monkeypatch)

    async def run():
        return await RECORD_EVENT_TOOL.execute(structured_record_event_arguments())

    with pytest.raises(ValueError, match="requires chat execution context"):
        asyncio.run(run())


@pytest.mark.parametrize("original_text", ["", "   ", 123, None])
def test_record_event_tool_rejects_missing_or_empty_original_text(original_text):
    arguments = structured_record_event_arguments()
    arguments["original_text"] = original_text

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid event data"):
        asyncio.run(run())


def test_record_event_tool_accepts_absolute_datetime(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "year": {"kind": "absolute", "value": 2026},
        "month": {"kind": "absolute", "value": 6},
        "day_selection": {
            "mode": "day",
            "day": {"kind": "absolute", "value": 29},
        },
        "hour": {"kind": "absolute", "value": 8},
        "minute": {"kind": "absolute", "value": 15},
        "precision": "exact",
        "timezone": "Europe/Zurich",
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 29, 6, 15, tzinfo=UTC)
    assert persisted_event.event_date_granularity == "minute"
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_accepts_absolute_date(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "year": {"kind": "absolute", "value": 2026},
        "month": {"kind": "absolute", "value": 6},
        "day_selection": {
            "mode": "day",
            "day": {"kind": "absolute", "value": 29},
        },
        "hour": None,
        "minute": None,
        "precision": "exact",
        "timezone": None,
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 29, 0, 0, tzinfo=UTC)
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_accepts_fuzzy_relative_datetime(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "year": None,
        "month": None,
        "day_selection": {
            "mode": "week",
            "week": {"kind": "relative", "value": -3},
            "weekday": None,
        },
        "hour": None,
        "minute": None,
        "precision": "fuzzy",
        "timezone": None,
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 8, 0, 0, tzinfo=UTC)
    assert persisted_event.event_date_granularity == "week"
    assert persisted_event.event_date_precision == "fuzzy"
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_accepts_relative_clock_datetime(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "year": None,
        "month": None,
        "day_selection": None,
        "hour": None,
        "minute": {"kind": "relative", "value": -30},
        "precision": "exact",
        "timezone": None,
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 29, 11, 30, tzinfo=UTC)
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_resolves_yesterday_at_absolute_hour(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "year": None,
        "month": None,
        "day_selection": {
            "mode": "day",
            "day": {"kind": "relative", "value": -1},
        },
        "hour": {"kind": "absolute", "value": 20},
        "minute": None,
        "precision": "exact",
        "timezone": "Europe/Zurich",
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 28, 18, 0, tzinfo=UTC)
    assert persisted_event.event_date_granularity == "hour"
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_resolves_fifth_of_last_month(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "year": None,
        "month": {"kind": "relative", "value": -1},
        "day_selection": {
            "mode": "day",
            "day": {"kind": "absolute", "value": 5},
        },
        "hour": None,
        "minute": None,
        "precision": "exact",
        "timezone": "Europe/Zurich",
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 5, 4, 22, 0, tzinfo=UTC)
    assert persisted_event.event_date_granularity == "day"
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_resolves_thursday_of_last_week(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(
        monkeypatch,
        now=datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
    )
    arguments = structured_record_event_arguments()
    arguments["original_text"] = "The flood happened on Thursday of last week"
    arguments["event_name"] = "Flood"
    arguments["event_date"] = component_event_date_arguments(
        day_selection={
            "mode": "week",
            "week": {"kind": "relative", "value": -1},
            "weekday": 4,
        },
        timezone="Europe/Zurich",
    )

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(
        2026, 7, 15, 22, 0, tzinfo=UTC
    )
    assert persisted_event.event_date_granularity == "day"
    assert persisted_event.event_date_input == arguments["event_date"]
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_persists_interval_with_inclusive_end(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(
        monkeypatch,
        now=datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
    )
    arguments = structured_record_event_arguments()
    arguments["original_text"] = "We had a flood between the 4th of June and yesterday"
    arguments["event_name"] = "Flood"
    arguments["event_date"] = component_event_date_arguments(
        month={"kind": "absolute", "value": 6},
        day_selection={
            "mode": "day",
            "day": {"kind": "absolute", "value": 4},
        },
        timezone="Europe/Zurich",
    )
    arguments["event_end_date"] = component_event_date_arguments(
        day_selection={
            "mode": "day",
            "day": {"kind": "relative", "value": -1},
        },
        timezone="Europe/Zurich",
    )

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 3, 22, 0, tzinfo=UTC)
    assert persisted_event.event_end_datetime == datetime(
        2026,
        7,
        20,
        21,
        59,
        59,
        999999,
        tzinfo=UTC,
    )
    assert persisted_event.event_end_date_granularity == "day"
    assert persisted_event.event_end_date_precision == "exact"
    assert persisted_event.event_end_date_input == arguments["event_end_date"]
    assert output == expected_record_event_tool_output(persisted_event)


@pytest.mark.parametrize(
    "invalid_end_kind",
    ["missing_start", "unknown_end"],
)
def test_record_event_tool_rejects_end_without_known_dates(invalid_end_kind):
    arguments = structured_record_event_arguments()
    known_date = component_event_date_arguments(
        day_selection={
            "mode": "day",
            "day": {"kind": "relative", "value": -1},
        }
    )
    unknown_date = component_event_date_arguments(precision="unknown")
    if invalid_end_kind == "missing_start":
        arguments["event_date"] = unknown_date
        arguments["event_end_date"] = known_date
    else:
        arguments["event_end_date"] = unknown_date

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid event data"):
        asyncio.run(run())


def test_record_event_tool_rejects_end_before_start(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = component_event_date_arguments(
        month={"kind": "absolute", "value": 6},
        day_selection={
            "mode": "day",
            "day": {"kind": "absolute", "value": 10},
        },
    )
    arguments["event_end_date"] = component_event_date_arguments(
        month={"kind": "absolute", "value": 6},
        day_selection={
            "mode": "day",
            "day": {"kind": "absolute", "value": 5},
        },
    )

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    with pytest.raises(ValueError, match="event end date must be after"):
        asyncio.run(run())


def test_record_event_tool_accepts_fuzzy_start_for_interval():
    arguments = structured_record_event_arguments()
    arguments["event_date"] = component_event_date_arguments(
        month={"kind": "relative", "value": -1},
        precision="fuzzy",
    )
    arguments["event_end_date"] = component_event_date_arguments(
        day_selection={
            "mode": "day",
            "day": {"kind": "relative", "value": -1},
        }
    )

    validated = events_tool_module.RecordEventToolInput.model_validate(arguments)
    assert validated.event_date.precision == "fuzzy"
    assert validated.event_end_date is not None


def test_record_event_tool_accepts_unknown_datetime(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "year": None,
        "month": None,
        "day_selection": None,
        "hour": None,
        "minute": None,
        "precision": "unknown",
        "timezone": None,
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime is None
    assert output == expected_record_event_tool_output(persisted_event)


@pytest.mark.parametrize(
    "event_date",
    [
        {
            "year": None,
            "month": None,
            "day_selection": None,
            "hour": None,
            "minute": None,
            "precision": "exact",
            "timezone": None,
        },
        {
            "year": None,
            "month": None,
            "day_selection": {
                "mode": "day",
                "day": {"kind": "absolute", "value": 32},
            },
            "hour": None,
            "minute": None,
            "precision": "exact",
            "timezone": None,
        },
        {
            "year": None,
            "month": {"kind": "absolute", "value": 13},
            "day_selection": None,
            "hour": None,
            "minute": None,
            "precision": "exact",
            "timezone": None,
        },
        {
            "year": None,
            "month": None,
            "day_selection": {
                "mode": "week",
                "week": {"kind": "absolute", "value": 1},
                "weekday": None,
            },
            "hour": None,
            "minute": None,
            "precision": "exact",
            "timezone": None,
        },
        {
            "year": None,
            "month": None,
            "day_selection": {
                "mode": "day",
                "day": {"kind": "relative", "value": -1},
            },
            "hour": None,
            "minute": None,
            "precision": "unknown",
            "timezone": None,
        },
        {
            "year": None,
            "month": None,
            "day_selection": {
                "mode": "day",
                "day": {"kind": "relative", "value": -1},
            },
            "hour": None,
            "minute": None,
            "precision": "exact",
            "timezone": "Not/A_Timezone",
        },
    ],
)
def test_record_event_tool_rejects_invalid_event_date(event_date):
    arguments = structured_record_event_arguments()
    arguments["event_date"] = event_date

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid event data"):
        asyncio.run(run())


def test_record_event_tool_rejects_non_string_tags():
    arguments = structured_record_event_arguments()
    arguments["tags"] = ["health_incident", 123]

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid event data"):
        asyncio.run(run())


@pytest.mark.parametrize(
    "tags",
    [
        [],
        ["not_a_fixed_tag"],
        ["health_incident", "health_incident"],
        ["health_incident", "other"],
    ],
)
def test_record_event_tool_rejects_invalid_fixed_tags(tags):
    arguments = structured_record_event_arguments()
    arguments["tags"] = tags

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid event data"):
        asyncio.run(run())


def test_record_event_tool_rejects_missing_tags():
    arguments = structured_record_event_arguments()
    del arguments["tags"]

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid event data"):
        asyncio.run(run())


@pytest.mark.parametrize(
    "field_name",
    ["affected_profession_categories", "response_profession_categories"],
)
def test_record_event_tool_rejects_invalid_profession_categories(field_name):
    arguments = structured_record_event_arguments()
    arguments[field_name] = ["not_a_profession_category"]

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments)

    with pytest.raises(ValueError, match="invalid event data"):
        asyncio.run(run())


def test_record_event_tool_accepts_empty_keyword_and_profession_lists(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["keywords"] = []
    arguments["affected_profession_categories"] = []
    arguments["response_profession_categories"] = []

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.keywords == []
    assert persisted_event.affected_profession_categories == []
    assert persisted_event.response_profession_categories == []


def test_recall_events_tool_rejects_unknown_or_duplicate_fixed_tags():
    async def run(tags):
        return await RECALL_EVENTS_TOOL.execute(
            {
                "keyword": None,
                "date_start": None,
                "date_end": None,
                "tags": tags,
                "tag_match": "all",
                "limit": 10,
            },
            record_event_tool_context(),
        )

    with pytest.raises(ValueError, match="invalid query data"):
        asyncio.run(run(["not_a_fixed_tag"]))
    with pytest.raises(ValueError, match="invalid query data"):
        asyncio.run(run(["health_incident", "health_incident"]))


def component_event_date_input(
    **overrides: object,
) -> events_tool_module.RecordEventDateInput:
    return events_tool_module.RecordEventDateInput.model_validate(
        component_event_date_arguments(**overrides)
    )


def test_resolve_component_datetime_handles_calendar_and_clock_units():
    reference = datetime(2026, 6, 29, 12, 0, tzinfo=UTC)
    event_date = component_event_date_input(
        year={"kind": "relative", "value": -1},
        month={"kind": "relative", "value": -2},
        day_selection={
            "mode": "day",
            "day": {"kind": "relative", "value": -3},
        },
        hour={"kind": "relative", "value": -4},
        minute={"kind": "relative", "value": -5},
    )

    resolved = event_date.resolve_event_datetime(reference)
    assert resolved is not None
    assert resolved.isoformat() == "2025-04-26T07:55:00+00:00"


def test_resolve_component_datetime_rejects_invalid_absolute_day():
    event_date = component_event_date_input(
        year={"kind": "absolute", "value": 2026},
        month={"kind": "absolute", "value": 2},
        day_selection={
            "mode": "day",
            "day": {"kind": "absolute", "value": 31},
        },
    )

    with pytest.raises(ValueError, match="absolute day is invalid"):
        event_date.resolve_event_datetime(datetime(2026, 1, 1, tzinfo=UTC))


def test_resolve_component_datetime_rejects_nonexistent_dst_time():
    event_date = component_event_date_input(
        year={"kind": "absolute", "value": 2026},
        month={"kind": "absolute", "value": 3},
        day_selection={
            "mode": "day",
            "day": {"kind": "absolute", "value": 29},
        },
        hour={"kind": "absolute", "value": 2},
        minute={"kind": "absolute", "value": 30},
        timezone="Europe/Zurich",
    )

    with pytest.raises(ValueError, match="nonexistent local time"):
        event_date.resolve_event_datetime(datetime(2026, 1, 1, tzinfo=UTC))


def test_resolve_component_datetime_uses_earlier_ambiguous_dst_time():
    event_date = component_event_date_input(
        year={"kind": "absolute", "value": 2026},
        month={"kind": "absolute", "value": 10},
        day_selection={
            "mode": "day",
            "day": {"kind": "absolute", "value": 25},
        },
        hour={"kind": "absolute", "value": 2},
        minute={"kind": "absolute", "value": 30},
        timezone="Europe/Zurich",
    )

    resolved = event_date.resolve_event_datetime(datetime(2026, 1, 1, tzinfo=UTC))
    assert resolved is not None
    assert resolved.fold == 0
    assert resolved.astimezone(UTC) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


def test_resolve_relative_hour_uses_elapsed_time_across_dst():
    event_date = component_event_date_input(
        hour={"kind": "relative", "value": 1},
        timezone="Europe/Zurich",
    )

    resolved = event_date.resolve_event_datetime(
        datetime(2026, 3, 29, 0, 30, tzinfo=UTC)
    )
    assert resolved is not None
    assert resolved.isoformat() == "2026-03-29T03:30:00+02:00"


@pytest.mark.parametrize(
    ("components", "expected"),
    [
        (
            {"year": {"kind": "absolute", "value": 2026}},
            "2026-12-31T23:59:59.999999+00:00",
        ),
        (
            {
                "year": {"kind": "absolute", "value": 2026},
                "month": {"kind": "absolute", "value": 2},
            },
            "2026-02-28T23:59:59.999999+00:00",
        ),
        (
            {
                "day_selection": {
                    "mode": "week",
                    "week": {"kind": "relative", "value": 0},
                    "weekday": None,
                }
            },
            "2026-07-26T23:59:59.999999+00:00",
        ),
        (
            {
                "day_selection": {
                    "mode": "day",
                    "day": {"kind": "absolute", "value": 21},
                }
            },
            "2026-07-21T23:59:59.999999+00:00",
        ),
    ],
)
def test_resolve_calendar_end_uses_inclusive_period_end(components, expected):
    event_date = component_event_date_input(**components)
    resolved = event_date.resolve_event_datetime(
        datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
        boundary="end",
    )
    assert resolved is not None
    assert resolved.isoformat() == expected


def test_resolve_clock_end_remains_exact():
    event_date = component_event_date_input(
        day_selection={
            "mode": "day",
            "day": {"kind": "relative", "value": 1},
        },
        hour={"kind": "absolute", "value": 20},
        timezone="Europe/Zurich",
    )
    resolved = event_date.resolve_event_datetime(
        datetime(2026, 7, 21, 12, 37, 42, tzinfo=UTC),
        boundary="end",
    )
    assert resolved is not None
    assert resolved.isoformat() == "2026-07-22T20:00:00+02:00"


@pytest.mark.parametrize(
    ("week_offset", "reference", "expected"),
    [
        (-1, datetime(2026, 7, 21, 12, 0, tzinfo=UTC), "2026-07-16"),
        (0, datetime(2026, 7, 21, 12, 0, tzinfo=UTC), "2026-07-23"),
        (-1, datetime(2026, 1, 2, 12, 0, tzinfo=UTC), "2025-12-25"),
    ],
)
def test_resolve_iso_weekday_within_relative_week(week_offset, reference, expected):
    event_date = component_event_date_input(
        day_selection={
            "mode": "week",
            "week": {"kind": "relative", "value": week_offset},
            "weekday": 4,
        }
    )

    resolved = event_date.resolve_event_datetime(reference)
    assert resolved is not None
    assert resolved.date().isoformat() == expected
    assert resolved.hour == 0
    assert event_date.granularity == "day"


def test_resolve_weekday_end_uses_inclusive_day_end():
    event_date = component_event_date_input(
        day_selection={
            "mode": "week",
            "week": {"kind": "relative", "value": -1},
            "weekday": 4,
        },
        timezone="Europe/Zurich",
    )

    resolved = event_date.resolve_event_datetime(
        datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
        boundary="end",
    )
    assert resolved is not None
    assert resolved.isoformat() == "2026-07-16T23:59:59.999999+02:00"


def test_resolve_weekday_with_clock_remains_exact():
    event_date = component_event_date_input(
        day_selection={
            "mode": "week",
            "week": {"kind": "relative", "value": -1},
            "weekday": 4,
        },
        hour={"kind": "absolute", "value": 20},
        timezone="Europe/Zurich",
    )

    resolved = event_date.resolve_event_datetime(
        datetime(2026, 7, 21, 12, 37, 42, tzinfo=UTC),
        boundary="end",
    )
    assert resolved is not None
    assert resolved.isoformat() == "2026-07-16T20:00:00+02:00"


@pytest.mark.parametrize("weekday", [0, 8])
def test_week_selection_rejects_invalid_iso_weekday(weekday):
    with pytest.raises(ValueError, match="weekday"):
        component_event_date_input(
            day_selection={
                "mode": "week",
                "week": {"kind": "relative", "value": -1},
                "weekday": weekday,
            }
        )
