from collections.abc import AsyncIterator
from typing import Sequence, cast

from openai.types.responses import (
    EasyInputMessageParam,
    ResponseInputParam,
    ResponseReasoningTextDeltaEvent,
    ResponseTextDeltaEvent,
)

from api.agent.openai import openai_client
from api.config import config
from api.models.chat import (
    CHUNK_TYPE_MESSAGE_CONTENT,
    CHUNK_TYPE_REASONING_TEXT,
    MESSAGE_STATUS_COMPLETE,
    ChatMessageResponse,
)
from api.services.chat_room.chat_assistant import (
    AssistantStreamChunkDelta,
    ChatAssistant,
)

ModelInputMessage = EasyInputMessageParam


class HumConnectAssistant(ChatAssistant):
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
    ) -> AsyncIterator[AssistantStreamChunkDelta]:
        model_input: ResponseInputParam = [
            *self.chat_history_to_model_input(chat_history),
            {
                "role": "user",
                "content": question,
            },
        ]
        stream = await openai_client.responses.create(
            input=model_input,
            model=config.MODEL_NAME,
            stream=True,
            text={"format": {"type": "json_object"}},
        )

        chunk_index = 0
        last_chunk_type = None

        async for event in stream:
            if event.type == "response.output_text.delta":
                chunk_type = CHUNK_TYPE_MESSAGE_CONTENT
                delta = cast(ResponseTextDeltaEvent, event).delta
            elif event.type == "response.reasoning_text.delta":
                chunk_type = CHUNK_TYPE_REASONING_TEXT
                delta = cast(ResponseReasoningTextDeltaEvent, event).delta
            else:
                continue

            if last_chunk_type is not None and chunk_type != last_chunk_type:
                chunk_index += 1

            yield AssistantStreamChunkDelta(
                chunk_index,
                chunk_type,
                delta,
            )
            last_chunk_type = chunk_type
