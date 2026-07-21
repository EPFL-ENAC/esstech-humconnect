import pytest

from tests.chat_room_helpers import *  # noqa: F403


@pytest.fixture(autouse=True)
def use_ready_default_tool_set(monkeypatch):
    from api.services.chat_room.default_tool_set import DEFAULT_LOCAL_TOOLS
    from api.services.chat_room.tools import ToolSet

    tool_set = ToolSet(DEFAULT_LOCAL_TOOLS)
    monkeypatch.setattr(
        humconnect_assistant_module,
        "HUMCONNECT_TOOL_SET",
        tool_set,
    )
    return tool_set


def test_humconnect_assistants_share_default_tool_set(use_ready_default_tool_set):
    first = HumConnectAssistant()
    second = HumConnectAssistant()

    assert first._tool_set is use_ready_default_tool_set
    assert second._tool_set is use_ready_default_tool_set


def test_humconnect_chat_assistant_converts_complete_history_for_model():
    chat_id = uuid4()
    messages = [
        ChatMessageResponse.from_db_model(
            make_db_message(
                chat_id, MESSAGE_ROLE_USER, "Hello", MESSAGE_STATUS_COMPLETE
            )
        ),
        ChatMessageResponse.from_db_model(
            make_db_message(
                chat_id=chat_id,
                role=MESSAGE_ROLE_ASSISTANT,
                content="Hi",
                status=MESSAGE_STATUS_COMPLETE,
            )
        ),
        ChatMessageResponse.from_db_model(
            make_db_message(
                chat_id=chat_id,
                role=MESSAGE_ROLE_ASSISTANT,
                content="Still typing",
                status=MESSAGE_STATUS_STREAMING,
            )
        ),
        ChatMessageResponse.from_db_model(
            make_db_message(
                chat_id=chat_id,
                role=MESSAGE_ROLE_ASSISTANT,
                content="Failed",
                status=MESSAGE_STATUS_ERROR,
            )
        ),
    ]

    model_input = HumConnectAssistant.chat_history_to_model_input(messages)

    assert model_input == [
        {
            "role": MESSAGE_ROLE_USER,
            "content": "Hello",
        },
        {
            "role": MESSAGE_ROLE_ASSISTANT,
            "content": "Hi",
        },
    ]


def test_user_profile_prompt_context_formats_prompt_safe_fields():
    profile = UserProfile(
        keycloak_sub="user-1",
        email="field@example.test",
        username=" field-lead ",
        first_name=" Ada ",
        last_name=" Lovelace ",
        profession="Clinician",
        profession_category="medical_clinical",
        center_address="Geneva logistics hub",
        center_latitude=46.2044,
        center_longitude=6.1432,
        action_radius_km=25,
        location_extra="Can cover nearby clinics",
        organisation="HumConnect",
        mother_tongue="en",
    )

    prompt_text = UserProfilePromptContext.from_db_model(profile).to_prompt_text()

    assert "- Name: Ada Lovelace" in prompt_text
    assert "- Username: field-lead" in prompt_text
    assert "- Profession: Clinician" in prompt_text
    assert "- Profession category: medical_clinical" in prompt_text
    assert "- Organisation: HumConnect" in prompt_text
    assert "- Mother tongue: en" in prompt_text
    assert "- Operating location: Geneva logistics hub" in prompt_text
    assert "- Action radius: 25 km" in prompt_text
    assert "- Location notes: Can cover nearby clinics" in prompt_text
    assert "field@example.test" not in prompt_text
    assert "46.2044" not in prompt_text
    assert "6.1432" not in prompt_text


def test_user_profile_prompt_context_omits_empty_fields():
    profile = UserProfile(
        keycloak_sub="user-1",
        username="",
        profession="  ",
    )

    prompt_text = UserProfilePromptContext.from_db_model(profile).to_prompt_text()

    assert prompt_text == ""


def test_humconnect_chat_assistant_streams_openai_text_deltas(monkeypatch):
    class FakeEvent:
        def __init__(
            self,
            event_type,
            delta="",
            item_id=None,
            output_index=0,
            content_index=0,
            item=None,
        ):
            self.type = event_type
            self.delta = delta
            self.item_id = item_id
            self.output_index = output_index
            self.content_index = content_index
            self.item = item

    class FakeResponses:
        def __init__(self):
            self.create_kwargs = None

        async def create(self, **kwargs):
            self.create_kwargs = kwargs

            async def stream():
                yield FakeEvent("response.created")
                yield FakeEvent(
                    "response.reasoning_text.delta", "Think", "reasoning-item"
                )
                yield FakeEvent("response.output_text.delta", "Hel", "message-item")
                yield FakeEvent("response.output_text.delta", "lo", "message-item")

            return stream()

    class FakeOpenAIClient:
        def __init__(self):
            self.responses = FakeResponses()

    fake_client = FakeOpenAIClient()
    monkeypatch.setattr(humconnect_assistant_module, "openai_client", fake_client)
    assistant = HumConnectAssistant()
    chat_id = uuid4()
    history = [
        ChatMessageResponse.from_db_model(
            make_db_message(
                chat_id=chat_id,
                role=MESSAGE_ROLE_USER,
                content="Earlier question",
                status=MESSAGE_STATUS_COMPLETE,
            )
        ),
        ChatMessageResponse.from_db_model(
            make_db_message(
                chat_id=chat_id,
                role=MESSAGE_ROLE_ASSISTANT,
                content="Earlier answer",
                status=MESSAGE_STATUS_COMPLETE,
            )
        ),
    ]

    async def run():
        return [
            chunk async for chunk in assistant.stream_response(history, "Say hello")
        ]

    assert asyncio.run(run()) == [
        AssistantStreamChunkDelta(0, CHUNK_TYPE_REASONING_TEXT, "Think"),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "Hel"),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "lo"),
    ]
    assert fake_client.responses.create_kwargs["stream"] is True
    assert [tool["name"] for tool in fake_client.responses.create_kwargs["tools"]] == [
        "dummy_tool",
        "ask_meditron",
        "ask_legitron",
        "record_event",
        "recall_events",
        "get_natural_events_context",
        "get_humanitarian_context",
        "create_analysis",
        "save_why_question",
        "save_why_answer",
        "get_analysis",
        "set_root_cause",
        "list_analyses",
    ]
    assert fake_client.responses.create_kwargs["input"] == [
        {
            "role": MESSAGE_ROLE_USER,
            "content": "Earlier question",
        },
        {
            "role": MESSAGE_ROLE_ASSISTANT,
            "content": "Earlier answer",
        },
        {
            "role": "user",
            "content": "Say hello",
        },
    ]


def test_humconnect_chat_assistant_adds_user_profile_to_instructions(monkeypatch):
    class FakeEvent:
        def __init__(self, event_type, delta=""):
            self.type = event_type
            self.delta = delta

    class FakeResponses:
        def __init__(self):
            self.create_kwargs = None

        async def create(self, **kwargs):
            self.create_kwargs = kwargs

            async def stream():
                yield FakeEvent("response.output_text.delta", "Hello")

            return stream()

    class FakeOpenAIClient:
        def __init__(self):
            self.responses = FakeResponses()

    fake_client = FakeOpenAIClient()
    monkeypatch.setattr(humconnect_assistant_module, "openai_client", fake_client)
    assistant = HumConnectAssistant()
    tool_context = ToolExecutionContext(
        chat_id=uuid4(),
        user_id=TEST_USER_ID,
        source_message_id=uuid4(),
        user_profile_context=UserProfilePromptContext(
            full_name="Ada Lovelace",
            username="field-lead",
            profession="Clinician",
            center_address="Geneva logistics hub",
        ),
    )

    async def run():
        return [
            chunk
            async for chunk in assistant.stream_response(
                [],
                "Say hello",
                tool_context,
            )
        ]

    assert asyncio.run(run()) == [
        AssistantStreamChunkDelta(0, CHUNK_TYPE_MESSAGE_CONTENT, "Hello"),
    ]
    instructions = fake_client.responses.create_kwargs["instructions"]
    assert "Current user profile context:" in instructions
    assert "- Name: Ada Lovelace" in instructions
    assert "- Username: field-lead" in instructions
    assert "- Profession: Clinician" in instructions
    assert "- Operating location: Geneva logistics hub" in instructions
    assert "Do not treat it as patient or event information" in instructions


def test_tool_call_output_formats_json_and_reports_success_status():
    success = ToolCallOutput.from_success("Tool finished")
    failure = ToolCallOutput.from_failure("Tool failed")

    assert success.to_json() == '{"ok": true, "result": "Tool finished"}'
    assert success.is_successful() is True
    assert failure.to_json() == '{"ok": false, "error": "Tool failed"}'
    assert failure.is_successful() is False


def test_tool_call_input_item_preserves_function_call_optional_fields():
    function_call = ResponseFunctionToolCall(
        id="item_1",
        arguments='{"message": "hello"}',
        call_id="call_1",
        name="dummy_tool",
        type="function_call",
        status="completed",
    )

    input_item = ToolCallInputItem.from_function_call(function_call)

    assert input_item.to_openai_input_item() == {
        "type": "function_call",
        "id": "item_1",
        "call_id": "call_1",
        "name": "dummy_tool",
        "arguments": '{"message": "hello"}',
        "status": "completed",
    }


def test_humconnect_chat_assistant_executes_dummy_tool_calls(monkeypatch):
    fake_client = install_fake_openai_client(
        monkeypatch,
        [
            [
                FakeOpenAIStreamEvent(
                    "response.output_item.done",
                    item=ResponseFunctionToolCall(
                        arguments='{"message": "hello"}',
                        call_id="call_1",
                        name="dummy_tool",
                        type="function_call",
                        status="completed",
                    ),
                )
            ],
            [FakeOpenAIStreamEvent("response.output_text.delta", "Done")],
        ],
    )
    assistant = HumConnectAssistant()

    async def run():
        return [chunk async for chunk in assistant.stream_response([], "Use a tool")]

    assert asyncio.run(run()) == [
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="dummy_tool",
                tool_label="Dummy tool",
                call_id="call_1",
                arguments={"message": "hello"},
                status="running",
            ),
        ),
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="dummy_tool",
                tool_label="Dummy tool",
                call_id="call_1",
                arguments={"message": "hello"},
                status="finished",
                answer="Dummy tool received: hello",
            ),
        ),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "Done"),
    ]

    second_input = fake_client.responses.create_kwargs[1]["input"]
    assert second_input[-2] == {
        "type": "function_call",
        "call_id": "call_1",
        "name": "dummy_tool",
        "arguments": '{"message": "hello"}',
        "status": "completed",
    }
    assert second_input[-1] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": '{"ok": true, "result": "Dummy tool received: hello"}',
    }


def test_humconnect_chat_assistant_executes_ask_meditron_tool_calls(monkeypatch):
    meditron_calls = []

    class FakeMeditronResponse:
        def __init__(self, text):
            self.output_text = text

    async def fake_meditron_create(*, model, instructions, input):
        meditron_calls.append((instructions, input))
        return FakeMeditronResponse("Watery diarrhea and dehydration.")

    monkeypatch.setattr(
        meditron_tool_module.openai_client.responses,
        "create",
        fake_meditron_create,
    )

    fake_client = install_fake_openai_client(
        monkeypatch,
        [
            [
                FakeOpenAIStreamEvent(
                    "response.output_item.done",
                    item=ResponseFunctionToolCall(
                        arguments=(
                            '{"prompt": "What are cholera symptoms?", '
                            '"system_prompt": "Answer for a clinician."}'
                        ),
                        call_id="call_meditron",
                        name="ask_meditron",
                        type="function_call",
                        status="completed",
                    ),
                )
            ],
            [FakeOpenAIStreamEvent("response.output_text.delta", "Summarized")],
        ],
    )
    assistant = HumConnectAssistant()

    async def run():
        return [chunk async for chunk in assistant.stream_response([], "Use Meditron")]

    assert asyncio.run(run()) == [
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="ask_meditron",
                tool_label="Ask Meditron",
                call_id="call_meditron",
                arguments={
                    "prompt": "What are cholera symptoms?",
                    "system_prompt": "Answer for a clinician.",
                },
                status="running",
            ),
        ),
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="ask_meditron",
                tool_label="Ask Meditron",
                call_id="call_meditron",
                arguments={
                    "prompt": "What are cholera symptoms?",
                    "system_prompt": "Answer for a clinician.",
                },
                status="finished",
                answer="Watery diarrhea and dehydration.",
            ),
        ),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "Summarized"),
    ]

    second_input = fake_client.responses.create_kwargs[1]["input"]
    assert meditron_calls == [("Answer for a clinician.", "What are cholera symptoms?")]
    assert second_input[-2] == {
        "type": "function_call",
        "call_id": "call_meditron",
        "name": "ask_meditron",
        "arguments": (
            '{"prompt": "What are cholera symptoms?", '
            '"system_prompt": "Answer for a clinician."}'
        ),
        "status": "completed",
    }
    assert second_input[-1] == {
        "type": "function_call_output",
        "call_id": "call_meditron",
        "output": ('{"ok": true, "result": "Watery diarrhea and dehydration."}'),
    }


def test_humconnect_chat_assistant_executes_record_event_tool_calls(monkeypatch):
    FakeAsyncSession.reset()
    configure_recorded_event_service(monkeypatch)
    tool_arguments = structured_record_event_arguments()

    fake_client = install_fake_openai_client(
        monkeypatch,
        [
            [
                FakeOpenAIStreamEvent(
                    "response.output_item.done",
                    item=ResponseFunctionToolCall(
                        arguments=json.dumps(tool_arguments),
                        call_id="call_record_event",
                        name="record_event",
                        type="function_call",
                        status="completed",
                    ),
                )
            ],
            [FakeOpenAIStreamEvent("response.output_text.delta", "Noted")],
        ],
    )
    assistant = HumConnectAssistant()

    async def run():
        return [
            chunk
            async for chunk in assistant.stream_response(
                [],
                "Remember this",
                record_event_tool_context(),
            )
        ]

    chunks = asyncio.run(run())
    [persisted_event] = recorded_events()
    expected_output = expected_record_event_tool_output(persisted_event)
    assert chunks == [
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="record_event",
                tool_label="Record event",
                call_id="call_record_event",
                arguments=tool_arguments,
                status="running",
            ),
        ),
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="record_event",
                tool_label="Record event",
                call_id="call_record_event",
                arguments=tool_arguments,
                status="finished",
                answer=expected_output,
            ),
        ),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "Noted"),
    ]
    assert persisted_event.chat_id == RECORDED_EVENT_CHAT_ID
    assert persisted_event.initiated_by_user_id == TEST_USER_ID
    assert persisted_event.source_message_id == RECORDED_EVENT_SOURCE_MESSAGE_ID

    second_input = fake_client.responses.create_kwargs[1]["input"]
    assert second_input[-1] == {
        "type": "function_call_output",
        "call_id": "call_record_event",
        "output": json.dumps({"ok": True, "result": expected_output}),
    }


def test_humconnect_chat_assistant_reports_invalid_tool_arguments(monkeypatch):
    fake_client = install_fake_openai_client(
        monkeypatch,
        [
            [
                FakeOpenAIStreamEvent(
                    "response.output_item.done",
                    item=ResponseFunctionToolCall(
                        arguments='{"message": ""}',
                        call_id="call_1",
                        name="dummy_tool",
                        type="function_call",
                    ),
                )
            ],
            [FakeOpenAIStreamEvent("response.output_text.delta", "Recovered")],
        ],
    )
    assistant = HumConnectAssistant()

    async def run():
        return [chunk async for chunk in assistant.stream_response([], "Use a tool")]

    assert asyncio.run(run()) == [
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="dummy_tool",
                tool_label="Dummy tool",
                call_id="call_1",
                arguments={"message": ""},
                status="running",
            ),
        ),
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="dummy_tool",
                tool_label="Dummy tool",
                call_id="call_1",
                arguments={"message": ""},
                status="failed",
                error="dummy_tool requires a non-empty string message.",
            ),
        ),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "Recovered"),
    ]
    output = fake_client.responses.create_kwargs[1]["input"][-1]["output"]
    assert '"ok": false' in output
    assert "dummy_tool requires a non-empty string message" in output


def test_humconnect_chat_assistant_reports_malformed_tool_arguments(monkeypatch):
    fake_client = install_fake_openai_client(
        monkeypatch,
        [
            [
                FakeOpenAIStreamEvent(
                    "response.output_item.done",
                    item=ResponseFunctionToolCall(
                        arguments="{",
                        call_id="call_1",
                        name="dummy_tool",
                        type="function_call",
                    ),
                )
            ],
            [FakeOpenAIStreamEvent("response.output_text.delta", "Recovered")],
        ],
    )
    assistant = HumConnectAssistant()

    async def run():
        return [chunk async for chunk in assistant.stream_response([], "Use a tool")]

    chunks = asyncio.run(run())

    assert chunks[0] == AssistantStreamPayloadUpdate(
        0,
        CHUNK_TYPE_TOOL_CALL,
        ToolCallPayload(
            tool_name="dummy_tool",
            tool_label="Dummy tool",
            call_id="call_1",
            arguments=None,
            status="running",
        ),
    )
    assert isinstance(chunks[1], AssistantStreamPayloadUpdate)
    assert chunks[1].payload.arguments is None
    assert chunks[1].payload.status == "failed"
    assert chunks[1].payload.error is not None
    assert "Expecting property name" in chunks[1].payload.error


def test_humconnect_chat_assistant_reports_unknown_tool(monkeypatch):
    fake_client = install_fake_openai_client(
        monkeypatch,
        [
            [
                FakeOpenAIStreamEvent(
                    "response.output_item.done",
                    item=ResponseFunctionToolCall(
                        arguments='{"message": "hello"}',
                        call_id="call_1",
                        name="missing_tool",
                        type="function_call",
                    ),
                )
            ],
            [FakeOpenAIStreamEvent("response.output_text.delta", "Recovered")],
        ],
    )
    assistant = HumConnectAssistant()

    async def run():
        return [chunk async for chunk in assistant.stream_response([], "Use a tool")]

    assert asyncio.run(run()) == [
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="missing_tool",
                tool_label="missing_tool",
                call_id="call_1",
                arguments={"message": "hello"},
                status="running",
            ),
        ),
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="missing_tool",
                tool_label="missing_tool",
                call_id="call_1",
                arguments={"message": "hello"},
                status="failed",
                error="Unknown tool: missing_tool",
            ),
        ),
        AssistantStreamChunkDelta(1, CHUNK_TYPE_MESSAGE_CONTENT, "Recovered"),
    ]
    output = fake_client.responses.create_kwargs[1]["input"][-1]["output"]
    assert '"ok": false' in output
    assert "Unknown tool: missing_tool" in output
