import asyncio
import random
from collections.abc import AsyncIterator, Sequence
from typing import NamedTuple, Protocol

from api.models.chat import (
    CHUNK_TYPE_MESSAGE_CONTENT,
    ChatMessageResponse,
    MessageChunkType,
)

PLACEHOLDER_TOKEN_DELAY_SECONDS = 0.05


class AssistantStreamChunkDelta(NamedTuple):
    index: int
    type: MessageChunkType
    content_delta: str


class ChatAssistant(Protocol):
    def stream_response(
        self,
        chat_history: Sequence[ChatMessageResponse],
        question: str,
    ) -> AsyncIterator[AssistantStreamChunkDelta]:
        raise NotImplementedError


class PlaceholderChatAssistant(ChatAssistant):
    async def stream_response(
        self,
        chat_history: Sequence[ChatMessageResponse],
        question: str,
    ) -> AsyncIterator[AssistantStreamChunkDelta]:
        random_number = random.randint(0, 999999)
        response = f"Random number: {random_number}"
        for token in response:
            yield AssistantStreamChunkDelta(0, CHUNK_TYPE_MESSAGE_CONTENT, token)
            await asyncio.sleep(PLACEHOLDER_TOKEN_DELAY_SECONDS)
