import asyncio

from meditron_mcp.main import ask as ask_meditron
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.services.chat_room.tools.base import (
    HumConnectTool,
    ToolExecutionContext,
    pydantic_response_function_tool,
)
from api.utils.pydantic_types import NonEmptyString


class AskMeditronInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    prompt: NonEmptyString = Field(
        description="Medical or clinical question to ask Meditron."
    )
    system_prompt: str = Field(
        default="",
        description="Optional system instructions for Meditron.",
    )


async def execute_ask_meditron_tool(
    arguments: dict[str, object],
    context: ToolExecutionContext | None = None,
) -> str:
    try:
        query = AskMeditronInput.model_validate(arguments)
    except ValidationError as e:
        raise ValueError(f"ask_meditron received invalid query data: {e}") from e

    return await asyncio.to_thread(
        ask_meditron,
        prompt=query.prompt,
        system_prompt=query.system_prompt,
    )


ASK_MEDITRON_TOOL = HumConnectTool(
    name="ask_meditron",
    label="Ask Meditron",
    definition=pydantic_response_function_tool(
        AskMeditronInput,
        name="ask_meditron",
        description=(
            "Ask Meditron, a medical LLM trained on a curated medical corpus, "
            "for help with medical and clinical questions."
        ),
    ),
    execute=execute_ask_meditron_tool,
)
