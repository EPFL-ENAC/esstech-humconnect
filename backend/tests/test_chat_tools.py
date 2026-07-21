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
        return await GET_HUMANITARIAN_CONTEXT_TOOL.execute(
            {"country_name": " Haiti "}
        )

    result = json.loads(asyncio.run(run()))

    assert result["summary"]["counts"] == {
        "reports": 1,
        "disasters": 1,
    }
    assert result["country"] == "Haiti"
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
    assert disaster_timeout == 5


def test_get_humanitarian_context_tool_returns_partial_results(monkeypatch):
    def fake_post(url, *, params, json, timeout):
        if url.endswith("/reports"):
            raise reliefweb_client_module.requests.RequestException("timeout")

        return FakeReliefWebResponse({"data": []})

    monkeypatch.setattr(reliefweb_client_module.requests, "post", fake_post)

    async def run():
        return await GET_HUMANITARIAN_CONTEXT_TOOL.execute(
            {"country_name": "Sudan"}
        )

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
        return await GET_HUMANITARIAN_CONTEXT_TOOL.execute(
            {"country_name": "Sudan"}
        )

    with pytest.raises(ValueError, match="humanitarian context from ReliefWeb"):
        asyncio.run(run())


def test_get_humanitarian_context_tool_rejects_all_malformed_payloads(monkeypatch):
    def fake_post(url, *, params, json, timeout):
        return FakeReliefWebResponse({"not_data": []})

    monkeypatch.setattr(reliefweb_client_module.requests, "post", fake_post)

    async def run():
        return await GET_HUMANITARIAN_CONTEXT_TOOL.execute(
            {"country_name": "Sudan"}
        )

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


def test_record_event_tool_schema_exposes_relative_date_shape():
    parameters = RECORD_EVENT_TOOL.definition["parameters"]
    defs = parameters["$defs"]
    event_date_schema = defs["RecordEventDateInput"]
    relative_schema = defs["RecordEventRelativeDateInput"]

    assert RECORD_EVENT_TOOL.definition["type"] == "function"
    assert RECORD_EVENT_TOOL.definition["strict"] is True
    assert parameters["additionalProperties"] is False
    assert event_date_schema["additionalProperties"] is False
    assert relative_schema["additionalProperties"] is False
    assert parameters["properties"]["event_date"] == {
        "$ref": "#/$defs/RecordEventDateInput"
    }
    assert event_date_schema["required"] == [
        "kind",
        "granularity",
        "precision",
        "value",
        "relative",
    ]
    assert relative_schema["required"] == [
        "direction",
        "years",
        "months",
        "weeks",
        "days",
        "hours",
        "minutes",
        "precision",
    ]
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
    assert parameters["required"] == [
        "original_text",
        "event_name",
        "event_date",
        "event_location",
        "tags",
        "keywords",
        "affected_profession_categories",
        "response_profession_categories",
    ]
    assert event_date_schema["properties"]["value"]["description"].startswith(
        "For absolute dates"
    )
    assert relative_schema["properties"]["direction"]["enum"] == ["past", "future"]
    assert relative_schema["properties"]["days"]["anyOf"] == [
        {"minimum": 0, "type": "integer"},
        {"type": "null"},
    ]


def test_record_event_tool_accepts_json_stringified_structured_fields(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = json.dumps(arguments["event_date"])
    arguments["event_location"] = json.dumps(arguments["event_location"])
    arguments["tags"] = json.dumps(arguments["tags"])
    arguments["keywords"] = json.dumps(arguments["keywords"])
    arguments["affected_profession_categories"] = json.dumps(
        arguments["affected_profession_categories"]
    )
    arguments["response_profession_categories"] = json.dumps(
        arguments["response_profession_categories"]
    )

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    assert persisted_event.tags == ["health_incident"]
    assert persisted_event.keywords == ["symptom", "cough"]
    assert persisted_event.affected_profession_categories == ["medical_clinical"]
    assert persisted_event.response_profession_categories == ["medical_clinical"]
    assert output == expected_record_event_tool_output(persisted_event)


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
        "kind": "absolute",
        "granularity": "minute",
        "precision": "exact",
        "value": "2026-06-29T08:15:00+02:00",
        "relative": None,
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime is not None
    assert persisted_event.event_datetime.isoformat() == "2026-06-29T08:15:00+02:00"
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_accepts_absolute_date(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "kind": "absolute",
        "granularity": "day",
        "precision": "exact",
        "value": "2026-06-29",
        "relative": None,
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(
        2026, 6, 29, 0, 0, tzinfo=UTC
    )
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_accepts_fuzzy_relative_datetime(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"]["granularity"] = "week"
    arguments["event_date"]["precision"] = "fuzzy"
    arguments["event_date"]["relative"]["weeks"] = 3
    del arguments["event_date"]["relative"]["days"]
    arguments["event_date"]["relative"]["precision"] = "fuzzy"

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 8, 12, 0, tzinfo=UTC)
    assert persisted_event.event_date_precision == "fuzzy"
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_accepts_sparse_relative_datetime(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "kind": "relative",
        "granularity": "minute",
        "precision": "exact",
        "relative": {
            "direction": "past",
            "minutes": 30,
            "precision": "exact",
        },
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 29, 11, 30, tzinfo=UTC)
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_accepts_strict_nullable_relative_datetime(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "kind": "relative",
        "granularity": "minute",
        "precision": "exact",
        "value": None,
        "relative": {
            "direction": "past",
            "years": None,
            "months": None,
            "weeks": None,
            "days": None,
            "hours": None,
            "minutes": 30,
            "precision": "exact",
        },
    }

    async def run():
        return await RECORD_EVENT_TOOL.execute(arguments, record_event_tool_context())

    output = asyncio.run(run())
    [persisted_event] = recorded_events()
    assert persisted_event.event_datetime == datetime(2026, 6, 29, 11, 30, tzinfo=UTC)
    assert output == expected_record_event_tool_output(persisted_event)


def test_record_event_tool_accepts_unknown_datetime(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    arguments = structured_record_event_arguments()
    arguments["event_date"] = {
        "kind": "unknown",
        "granularity": "unknown",
        "precision": "unknown",
        "value": None,
        "relative": None,
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
            "kind": "relative",
            "granularity": "day",
            "precision": "exact",
            "relative": {
                "direction": "past",
                "precision": "exact",
            },
        },
        {
            "kind": "relative",
            "granularity": "day",
            "precision": "exact",
            "value": None,
            "relative": {
                "direction": "past",
                "years": None,
                "months": None,
                "weeks": None,
                "days": None,
                "hours": None,
                "minutes": None,
                "precision": "exact",
            },
        },
        {
            "kind": "relative",
            "granularity": "day",
            "precision": "exact",
            "relative": {
                "direction": "past",
                "days": -1,
                "precision": "exact",
            },
        },
        {
            "kind": "absolute",
            "granularity": "day",
            "precision": "exact",
            "value": None,
        },
        {
            "kind": "absolute",
            "granularity": "day",
            "precision": "exact",
            "value": "not-a-date",
        },
        {
            "kind": "unknown",
            "granularity": "day",
            "precision": "unknown",
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


def test_resolve_relative_datetime_handles_calendar_and_clock_units():
    reference = datetime(2026, 6, 29, 12, 0, tzinfo=UTC)
    relative = events_tool_module.RecordEventRelativeDateInput(
        direction="past",
        years=1,
        months=2,
        weeks=1,
        days=3,
        hours=4,
        minutes=5,
        precision="exact",
    )

    assert (
        relative.resolve_relative_to_datetime(reference).isoformat()
        == "2025-04-19T07:55:00+00:00"
    )
