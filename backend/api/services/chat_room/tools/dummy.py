from pydantic import BaseModel, ConfigDict, Field

from api.services.chat_room.tools.base import HumConnectTool
from api.utils.pydantic_types import NonEmptyString


class DummyToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    message: NonEmptyString = Field(
        description="Message to echo through the dummy tool."
    )


def _execute_dummy_tool(query: DummyToolInput) -> str:
    return f"Dummy tool received: {query.message}"


DUMMY_TOOL = HumConnectTool.from_sync_handler(
    name="dummy_tool",
    label="Dummy tool",
    input_model=DummyToolInput,
    description="A deterministic dummy tool for testing tool-call plumbing.",
    invalid_input_message="dummy_tool requires a non-empty string message.",
    handler=_execute_dummy_tool,
    include_validation_details=False,
)
