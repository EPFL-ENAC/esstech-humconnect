import asyncio
import random
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from api.models.chat import (
    CHUNK_TYPE_MESSAGE_CONTENT,
    ChatMessageResponse,
    MessageChunkType,
    ToolCallPayload,
)

PLACEHOLDER_TOKEN_DELAY_SECONDS = 0.05


@dataclass(frozen=True, slots=True)
class AssistantStreamChunkDelta:
    index: int
    type: MessageChunkType
    content_delta: str


@dataclass(frozen=True, slots=True)
class AssistantStreamPayloadUpdate:
    index: int
    type: MessageChunkType
    payload: ToolCallPayload


AssistantStreamEvent = AssistantStreamChunkDelta | AssistantStreamPayloadUpdate


class ChatAssistant(Protocol):
    def stream_response(
        self,
        chat_history: Sequence[ChatMessageResponse],
        question: str,
    ) -> AsyncIterator[AssistantStreamEvent]:
        raise NotImplementedError


class PlaceholderChatAssistant(ChatAssistant):
    async def stream_response(
        self,
        chat_history: Sequence[ChatMessageResponse],
        question: str,
    ) -> AsyncIterator[AssistantStreamEvent]:
        random_number = random.randint(0, 999999)
        response = f"Random number: {random_number}"
        for token in response:
            yield AssistantStreamChunkDelta(0, CHUNK_TYPE_MESSAGE_CONTENT, token)
            await asyncio.sleep(PLACEHOLDER_TOKEN_DELAY_SECONDS)
