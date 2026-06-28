import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Sequence, cast

from openai.types.responses import (
    EasyInputMessageParam,
    ResponseFunctionToolCall,
    ResponseInputItemParam,
    ResponseInputParam,
    ResponseReasoningTextDeltaEvent,
    ResponseTextDeltaEvent,
)

from api.agent.openai import openai_client
from api.config import config
from api.models.chat import (
    CHUNK_TYPE_MESSAGE_CONTENT,
    CHUNK_TYPE_REASONING_TEXT,
    CHUNK_TYPE_TOOL_CALL,
    MESSAGE_STATUS_COMPLETE,
    ChatMessageResponse,
    MessageChunkType,
    ToolCallPayload,
)
from api.services.chat_room.chat_assistant import (
    AssistantStreamChunkDelta,
    AssistantStreamEvent,
    AssistantStreamPayloadUpdate,
    ChatAssistant,
)
from api.services.chat_room.tools import ToolSet
from api.services.chat_room.tools.dummy import DUMMY_TOOL

ModelInputMessage = EasyInputMessageParam
MAX_TOOL_CALL_ROUNDS = 5


@dataclass(slots=True)
class StreamChunkCursor:
    chunk_index: int = 0
    last_chunk_type: MessageChunkType | None = None

    def next_delta(
        self,
        chunk_type: MessageChunkType,
        delta: str,
        *,
        force_new_chunk: bool = False,
    ) -> AssistantStreamChunkDelta:
        chunk_index = self.chunk_index
        if self.last_chunk_type is not None and (
            force_new_chunk or chunk_type != self.last_chunk_type
        ):
            chunk_index += 1

        self.chunk_index = chunk_index
        self.last_chunk_type = chunk_type

        return AssistantStreamChunkDelta(
            chunk_index,
            chunk_type,
            delta,
        )

    def next_chunk_index(
        self,
        chunk_type: MessageChunkType,
        *,
        force_new_chunk: bool = False,
    ) -> int:
        chunk_index = self.chunk_index
        if self.last_chunk_type is not None and (
            force_new_chunk or chunk_type != self.last_chunk_type
        ):
            chunk_index += 1

        self.chunk_index = chunk_index
        self.last_chunk_type = chunk_type
        return chunk_index


def parse_tool_arguments(raw_arguments: str) -> dict[str, Any] | None:
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError:
        return None

    if isinstance(arguments, dict):
        return arguments
    return None


class HumConnectAssistant(ChatAssistant):
    def __init__(self, tool_set: ToolSet | None = None) -> None:
        self._tool_set = tool_set or ToolSet(
            [
                DUMMY_TOOL,
            ]
        )

    @staticmethod
    def chat_history_to_model_input(
        chat_history: Sequence[ChatMessageResponse],
    ) -> list[ModelInputMessage]:
        return [
            message.to_ai_model_input()
            for message in chat_history
            if message.status == MESSAGE_STATUS_COMPLETE and message.content_for_model()
        ]

    async def stream_response(
        self,
        chat_history: Sequence[ChatMessageResponse],
        question: str,
    ) -> AsyncIterator[AssistantStreamEvent]:
        model_input: ResponseInputParam = [
            *self.chat_history_to_model_input(chat_history),
            {
                "role": "user",
                "content": question,
            },
        ]
        chunk_cursor = StreamChunkCursor()
        tool_call_rounds = 0

        while True:
            function_calls: list[ResponseFunctionToolCall] = []
            stream = await openai_client.responses.create(
                input=model_input,
                model=config.MODEL_NAME,
                stream=True,
                text={"format": {"type": "json_object"}},
                tools=self._tool_set.definitions(),
            )

            async for event in stream:
                if event.type == "response.output_text.delta":
                    chunk_type = CHUNK_TYPE_MESSAGE_CONTENT
                    delta = cast(ResponseTextDeltaEvent, event).delta
                elif event.type == "response.reasoning_text.delta":
                    chunk_type = CHUNK_TYPE_REASONING_TEXT
                    delta = cast(ResponseReasoningTextDeltaEvent, event).delta
                elif event.type == "response.output_item.done":
                    item = getattr(event, "item", None)
                    if getattr(item, "type", None) == "function_call":
                        function_calls.append(cast(ResponseFunctionToolCall, item))
                    continue
                else:
                    continue

                yield chunk_cursor.next_delta(
                    chunk_type,
                    delta,
                )

            if not function_calls:
                return

            if tool_call_rounds >= MAX_TOOL_CALL_ROUNDS:
                raise RuntimeError("Maximum tool-call rounds exceeded.")
            tool_call_rounds += 1

            tool_input_items: list[ResponseInputItemParam] = []
            for function_call in function_calls:
                tool_label = self._tool_set.label_for(function_call)
                tool_arguments = parse_tool_arguments(function_call.arguments)
                tool_chunk_index = chunk_cursor.next_chunk_index(
                    CHUNK_TYPE_TOOL_CALL,
                    force_new_chunk=True,
                )

                yield AssistantStreamPayloadUpdate(
                    tool_chunk_index,
                    CHUNK_TYPE_TOOL_CALL,
                    ToolCallPayload.from_running(
                        tool_name=function_call.name,
                        tool_label=tool_label,
                        call_id=function_call.call_id,
                        arguments=tool_arguments,
                    ),
                )

                tool_execution = await self._tool_set.execute(function_call)
                if tool_execution.succeeded:
                    payload = ToolCallPayload.from_finished(
                        tool_name=function_call.name,
                        tool_label=tool_execution.label,
                        call_id=function_call.call_id,
                        arguments=tool_arguments,
                        answer=tool_execution.output,
                    )
                else:
                    payload = ToolCallPayload.from_failed(
                        tool_name=function_call.name,
                        tool_label=tool_execution.label,
                        call_id=function_call.call_id,
                        arguments=tool_arguments,
                        error=tool_execution.output,
                    )

                yield AssistantStreamPayloadUpdate(
                    tool_chunk_index,
                    CHUNK_TYPE_TOOL_CALL,
                    payload,
                )

                tool_input_items.append(tool_execution.function_call_input_item)
                tool_input_items.append(tool_execution.function_call_output_input_item)

            model_input = [*model_input, *tool_input_items]
