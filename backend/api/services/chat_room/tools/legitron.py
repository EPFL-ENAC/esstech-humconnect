from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from api.config import config
from api.services.chat_room.tools.base import (
    HumConnectTool,
)
from api.utils.pydantic_types import NonEmptyString

openai_client = OpenAI(
    base_url=config.OPENAI_API_URL,
    api_key=config.OPENAI_API_KEY_PREMIUM,
)


class AskLegitronInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    prompt: NonEmptyString = Field(
        description="Humanitarian legal question to ask Legitron."
    )
    system_prompt: str = Field(
        default="",
        description="Optional system instructions for Legitron.",
    )


def _ask_legitron(query: AskLegitronInput) -> str:
    response = openai_client.responses.create(
        model=config.LEGITRON_MODEL_NAME,
        instructions=query.system_prompt,
        input=query.prompt,
    )

    return response.output_text


ASK_LEGITRON_TOOL = HumConnectTool.from_sync_handler(
    name="ask_legitron",
    label="Ask Legitron",
    input_model=AskLegitronInput,
    description=(
        "Ask Legitron, an LLM trained on a legal corpus of humanitarian organizations guidelines and international laws."
    ),
    invalid_input_message="ask_legitron received invalid query data",
    handler=_ask_legitron,
)
