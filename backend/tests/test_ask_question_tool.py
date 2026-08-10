import json

from api.models.chat import CHUNK_TYPE_TOOL_CALL, ToolCallPayload
from api.services.chat_room.humconnect_assistant import HumConnectAssistant
from api.services.chat_room.tools import ASK_QUESTION_TOOL, ToolSet
from api.services.chat_room.tools import ask_question as ask_question_module
from api.services.chat_room.tools.base import ToolCallExecution
from tests.chat_room_helpers import *  # noqa: F403


def test_ask_question_tool_is_marked_terminal():
    assert ASK_QUESTION_TOOL.terminal is True


def test_ask_question_tool_returns_empty_string():
    async def run():
        return await ASK_QUESTION_TOOL.execute(
            {"question": "Where are you located?", "possible_answers": []}
        )

    assert asyncio.run(run()) == ""


def test_ask_question_tool_accepts_empty_possible_answers():
    async def run():
        return await ASK_QUESTION_TOOL.execute(
            {"question": "Describe the situation.", "possible_answers": []}
        )

    assert asyncio.run(run()) == ""


def test_ask_question_tool_accepts_possible_answers():
    async def run():
        return await ASK_QUESTION_TOOL.execute(
            {
                "question": "Which country?",
                "possible_answers": ["Haiti", "Sudan"],
            }
        )

    assert asyncio.run(run()) == ""


@pytest.mark.parametrize("question", ["", "   ", 123, None])
def test_ask_question_tool_rejects_missing_or_empty_question(question):
    async def run():
        return await ASK_QUESTION_TOOL.execute(
            {"question": question, "possible_answers": []}
        )

    with pytest.raises(ValueError, match="invalid question data"):
        asyncio.run(run())


@pytest.mark.parametrize(
    "possible_answers",
    ["not-a-list", ["", "Haiti"], ["Haiti", 123]],
)
def test_ask_question_tool_rejects_invalid_possible_answers(possible_answers):
    async def run():
        return await ASK_QUESTION_TOOL.execute(
            {"question": "Which country?", "possible_answers": possible_answers}
        )

    with pytest.raises(ValueError, match="invalid question data"):
        asyncio.run(run())


def test_ask_question_tool_rejects_unknown_fields():
    async def run():
        return await ASK_QUESTION_TOOL.execute(
            {
                "question": "Which country?",
                "possible_answers": [],
                "extra": "nope",
            }
        )

    with pytest.raises(ValueError, match="invalid question data"):
        asyncio.run(run())


def test_ask_question_tool_schema_is_strict_and_allows_empty_answers():
    parameters = ASK_QUESTION_TOOL.definition["parameters"]

    assert ASK_QUESTION_TOOL.definition["type"] == "function"
    assert ASK_QUESTION_TOOL.definition["strict"] is True
    assert parameters["additionalProperties"] is False
    assert parameters["required"] == ["question", "possible_answers"]
    assert parameters["properties"]["question"] == {
        "description": "The question to ask the user.",
        "minLength": 1,
        "title": "Question",
        "type": "string",
    }
    possible_answers_schema = parameters["properties"]["possible_answers"]
    assert possible_answers_schema["type"] == "array"
    assert possible_answers_schema["items"] == {"minLength": 1, "type": "string"}
    assert "minItems" not in possible_answers_schema


def test_ask_question_tool_execution_is_marked_terminal():
    tool_set = ToolSet([ASK_QUESTION_TOOL])

    function_call = ResponseFunctionToolCall(
        arguments='{"question": "Which country?", "possible_answers": ["Haiti"]}',
        call_id="call_ask",
        name="ask_question",
        type="function_call",
        status="completed",
    )

    async def run():
        return await tool_set.execute(function_call)

    execution = asyncio.run(run())
    assert isinstance(execution, ToolCallExecution)
    assert execution.terminal is True
    assert execution.succeeded is True
    assert execution.output == ""
    assert json.loads(execution.function_call_output_input_item["output"]) == {
        "ok": True,
        "result": "",
    }


def test_humconnect_assistant_ends_loop_after_ask_question(monkeypatch):
    fake_client = install_fake_openai_client(
        monkeypatch,
        [
            [
                FakeOpenAIStreamEvent(
                    "response.output_item.done",
                    item=ResponseFunctionToolCall(
                        arguments=json.dumps(
                            {
                                "question": "Which country are you in?",
                                "possible_answers": ["Haiti", "Sudan"],
                            }
                        ),
                        call_id="call_ask",
                        name="ask_question",
                        type="function_call",
                        status="completed",
                    ),
                )
            ],
        ],
    )
    assistant = HumConnectAssistant(tool_set=ToolSet([ASK_QUESTION_TOOL]))

    async def run():
        return [chunk async for chunk in assistant.stream_response([], "Help me")]

    chunks = asyncio.run(run())
    assert chunks == [
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="ask_question",
                tool_label="Ask question",
                call_id="call_ask",
                arguments={
                    "question": "Which country are you in?",
                    "possible_answers": ["Haiti", "Sudan"],
                },
                status="running",
            ),
        ),
        AssistantStreamPayloadUpdate(
            0,
            CHUNK_TYPE_TOOL_CALL,
            ToolCallPayload(
                tool_name="ask_question",
                tool_label="Ask question",
                call_id="call_ask",
                arguments={
                    "question": "Which country are you in?",
                    "possible_answers": ["Haiti", "Sudan"],
                },
                status="finished",
                answer="",
            ),
        ),
    ]
    # The terminal tool must end the loop: only one OpenAI round is performed.
    assert len(fake_client.responses.create_kwargs) == 1


def test_humconnect_assistant_ends_loop_after_ask_question_with_free_answer(
    monkeypatch,
):
    fake_client = install_fake_openai_client(
        monkeypatch,
        [
            [
                FakeOpenAIStreamEvent(
                    "response.output_item.done",
                    item=ResponseFunctionToolCall(
                        arguments=json.dumps(
                            {
                                "question": "Describe the symptoms.",
                                "possible_answers": [],
                            }
                        ),
                        call_id="call_ask",
                        name="ask_question",
                        type="function_call",
                        status="completed",
                    ),
                )
            ],
        ],
    )
    assistant = HumConnectAssistant(tool_set=ToolSet([ASK_QUESTION_TOOL]))

    async def run():
        return [chunk async for chunk in assistant.stream_response([], "Help me")]

    chunks = asyncio.run(run())
    assert len(chunks) == 2
    assert chunks[1].payload.status == "finished"
    assert chunks[1].payload.answer == ""
    assert len(fake_client.responses.create_kwargs) == 1


# Silence the unused-import linter for the helper wildcard import above.
_ = ask_question_module
