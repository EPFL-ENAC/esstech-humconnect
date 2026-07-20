from meditron_mcp.main import ask as ask_meditron
from pydantic import BaseModel, ConfigDict, Field

from api.services.chat_room.tools.base import (
    HumConnectTool,
)
from api.utils.pydantic_types import NonEmptyString


class AskMeditronInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    prompt: NonEmptyString = Field(
        description="Medical or clinical question to ask Meditron."
    )
    system_prompt: str = Field(
        default="You are a medical expert with deep knowledge of clinical science, medical guidelines, and evidence-based medicine. Answer the following question based on current standard medical practices. If uncertain, acknowledge the uncertainty rather than guessing.",
        description="Optional system instructions for Meditron.",
    )


def _ask_meditron(query: AskMeditronInput) -> str:
    return ask_meditron(
        prompt=query.prompt,
        system_prompt=query.system_prompt,
    )


ASK_MEDITRON_TOOL = HumConnectTool.from_sync_handler(
    name="ask_meditron",
    label="Ask Meditron",
    input_model=AskMeditronInput,
    description="Ask Meditron, a medical LLM trained on a curated medical corpus, for help with medical and clinical questions. Knowledge cutoff is August 2023.",
    invalid_input_message="ask_meditron received invalid query data",
    handler=_ask_meditron,
)
