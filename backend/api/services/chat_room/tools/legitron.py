from pydantic import BaseModel, ConfigDict, Field

from api.agent.openai import openai_client_premium
from api.config import config
from api.services.chat_room.tools.base import (
    HumConnectTool,
)
from api.utils.pydantic_types import NonEmptyString


class AskLegitronInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    prompt: NonEmptyString = Field(
        description="Humanitarian legal question to ask Legitron."
    )
    system_prompt: str = Field(
        default="",
        description="Optional system instructions for Legitron.",
    )


async def _ask_legitron(query: AskLegitronInput) -> str:
    response = await openai_client_premium.responses.create(
        model=config.LEGITRON_MODEL_NAME,
        instructions=query.system_prompt,
        input=query.prompt,
    )

    return response.output_text


ASK_LEGITRON_TOOL = HumConnectTool.from_async_handler(
    name="ask_legitron",
    label="Ask Legitron",
    input_model=AskLegitronInput,
    description=(
        "Ask Legitron, an LLM trained on a legal corpus of humanitarian organizations guidelines and international laws."
    ),
    invalid_input_message="ask_legitron received invalid query data",
    handler=_ask_legitron,
)
