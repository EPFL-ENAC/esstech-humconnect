from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Sequence, cast

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
from api.services.chat_room.default_tool_set import HUMCONNECT_TOOL_SET
from api.services.chat_room.tools import ToolSet, parse_tool_call_arguments
from api.services.chat_room.tools.base import ToolCallExecution, ToolExecutionContext

ModelInputMessage = EasyInputMessageParam
MAX_TOOL_CALL_ROUNDS = 10
BASE_INSTRUCTIONS = (
    "When the user states a problem, run a 5 Whys root cause analysis by calling "
    "the start_5_whys_analysis tool. Save each why level by calling save_why_step "
    "with both the question and its answer. "
    "Use the ask_question tool when you need to ask a single question to the user, "
    "for example during a 5 Whys analysis, or when you need to clarify something. "
    "Don't hesitate to record events when they could be useful for later queries. "
    "Events are used in a global context to help with emergencies, health hazard, etc. "
    "In the case that you don't have all the information needed to create an event, "
    "but you feel the user is giving you important enough information that would make "
    "creating one worth it, ask questions to the user until you can record the event. "
    "When you feel that the user is talking about something that could have been "
    "caused by a prior event, use the recall_events tool to retrieve potentially "
    "relevant events across chats. If you are unsure about the relevance of an event, "
    "you can still recall it and then decide whether to use it or not. When a user "
    "asks about nearby hazards, disasters, earthquakes, fires, storms, volcanoes, "
    "floods, or natural event context around a location, use the "
    "get_natural_events_context tool with the relevant center point and radius. "
    "When a user asks about outbreaks, epidemics, public-health reports, "
    "humanitarian crises, displacement, conflict, food insecurity, or "
    "ReliefWeb/OCHA/WHO-style country context, use the get_humanitarian_context "
    "tool with a country name. If the country is ambiguous and you cannot infer "
    "it confidently, ask the user which country they mean. "
    "For IPC/CH acute food-insecurity statistics, affected-population figures, "
    "prevalence comparisons, or the global WFP hunger situation, use the "
    "get_hunger_map_context tool. Pass an uppercase ISO 3166-1 alpha-2/alpha-3 "
    "country code, the WFP area code PSG or PSW, or 'global' for the headline "
    "and all available country estimates. Continue using "
    "get_humanitarian_context for broader narrative "
    "crisis reports and recent humanitarian developments. "
    "For WHO guidance, recommendations, manuals, research, or technical evidence, "
    "use search_who_publications. If a search result's abstract is insufficient, "
    "use get_who_publication_content with its item ID. Continue using "
    "get_humanitarian_context for recent outbreaks, disasters, and country-level "
    "crisis reports. "
    "For sanitation and humanitarian WASH questions, use the available SaniHub "
    "knowledge search tool. Retrieve relevant document pages with the SaniHub "
    "document content tool when the search results require deeper evidence. "
    "If you need to ask Meditron, a medical LLM trained on a curated medical "
    "corpus, make sure you gather all the relevant information from the user or "
    "the other tools to get better context. "
    "When you need a specific piece of information from the user before you can "
    "proceed, use the ask_question tool with a clear question and, when helpful, "
    "a list of possible answers to let the user pick from. Calling ask_question "
    "ends your current response, so never combine it with other tools or "
    "additional text in the same turn; the user's answer arrives as the next "
    "chat message."
)


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
        chunk_index = self.next_chunk_index(
            chunk_type,
            force_new_chunk=force_new_chunk,
        )

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


class HumConnectAssistant(ChatAssistant):
    def __init__(self, tool_set: ToolSet | None = None) -> None:
        self._tool_set = tool_set if tool_set is not None else HUMCONNECT_TOOL_SET

    @staticmethod
    def chat_history_to_model_input(
        chat_history: Sequence[ChatMessageResponse],
    ) -> list[ModelInputMessage]:
        items: list[ModelInputMessage] = []
        for message in chat_history:
            if message.status != MESSAGE_STATUS_COMPLETE:
                continue
            item = message.to_ai_model_input()
            if not item["content"]:
                # Terminal tool calls such as ask_question end the turn without
                # producing text. Surface the tool's output as the message
                # content so the exchange is preserved in the model's history.
                parts: list[str] = []
                for chunk in message.chunks:
                    if chunk.type != CHUNK_TYPE_TOOL_CALL or chunk.payload is None:
                        continue
                    if chunk.payload.answer:
                        parts.append(chunk.payload.answer)
                if parts:
                    item = cast(
                        ModelInputMessage,
                        {"role": item["role"], "content": "\n\n".join(parts)},
                    )
            if item["content"]:
                items.append(item)
        return items

    @staticmethod
    def instructions_for_context(
        tool_context: ToolExecutionContext | None,
    ) -> str:
        if tool_context is None or tool_context.user_profile_context is None:
            return BASE_INSTRUCTIONS

        profile_prompt = tool_context.user_profile_context.to_prompt_text()
        if not profile_prompt:
            return BASE_INSTRUCTIONS

        return (
            f"{BASE_INSTRUCTIONS}\n\n"
            "Current user profile context:\n"
            f"{profile_prompt}\n\n"
            "Use this as context about the current user. Do not treat it as patient "
            "or event information unless the user explicitly says it applies."
        )

    async def stream_response(
        self,
        chat_history: Sequence[ChatMessageResponse],
        question: str,
        tool_context: ToolExecutionContext | None = None,
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
                instructions=self.instructions_for_context(tool_context),
                text={"format": {"type": "json_object"}},
                tools=[*self._tool_set.definitions()],
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

            terminal_tool_called = False
            tool_executions: list[ToolCallExecution] = []
            for function_call in function_calls:
                tool_label = self._tool_set.label_for(function_call)
                tool_arguments = parse_tool_call_arguments(function_call.arguments)
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

                tool_execution = await self._tool_set.execute(
                    function_call,
                    tool_context,
                )
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

                tool_executions.append(tool_execution)
                if tool_execution.terminal:
                    terminal_tool_called = True

            tool_input_items: list[ResponseInputItemParam] = []
            for tool_execution in tool_executions:
                tool_input_items.append(tool_execution.function_call_input_item)
            for tool_execution in tool_executions:
                tool_input_items.append(tool_execution.function_call_output_input_item)

            if terminal_tool_called:
                return

            model_input = [*model_input, *tool_input_items]
