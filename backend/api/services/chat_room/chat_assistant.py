import asyncio
import random
from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from api.models.chat import ChatMessageResponse

PLACEHOLDER_TOKEN_DELAY_SECONDS = 0.05


class ChatAssistant(Protocol):
    def stream_response(
        self,
        chat_history: Sequence[ChatMessageResponse],
        question: str,
    ) -> AsyncIterator[str]:
        raise NotImplementedError


class PlaceholderChatAssistant:
    async def stream_response(
        self,
        chat_history: Sequence[ChatMessageResponse],
        question: str,
    ) -> AsyncIterator[str]:
        random_number = random.randint(0, 999999)
        response = f"Random number: {random_number}"
        for token in response:
            yield token
            await asyncio.sleep(PLACEHOLDER_TOKEN_DELAY_SECONDS)
