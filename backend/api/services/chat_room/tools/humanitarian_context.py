import asyncio

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.services.chat_room.tools.base import (
    HumConnectTool,
    ToolExecutionContext,
    pydantic_response_function_tool,
)
from api.services.humanitarian_context import HumanitarianContextPull
from api.utils.pydantic_types import NonEmptyString


class HumanitarianContextInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    country_name: NonEmptyString = Field(
        description="Country name to search in ReliefWeb, such as Haiti or Sudan."
    )


def _get_humanitarian_context(query: HumanitarianContextInput) -> str:
    return HumanitarianContextPull(query.country_name).run()


async def execute_get_humanitarian_context_tool(
    arguments: dict[str, object],
    context: ToolExecutionContext | None = None,
) -> str:
    try:
        query = HumanitarianContextInput.model_validate(arguments)
    except ValidationError as e:
        raise ValueError(
            f"get_humanitarian_context received invalid query data: {e}"
        ) from e

    return await asyncio.to_thread(_get_humanitarian_context, query)


GET_HUMANITARIAN_CONTEXT_TOOL = HumConnectTool(
    name="get_humanitarian_context",
    label="Get humanitarian context",
    definition=pydantic_response_function_tool(
        HumanitarianContextInput,
        name="get_humanitarian_context",
        description=(
            "Fetch recent country-level humanitarian, outbreak, public-health, "
            "displacement, conflict, and crisis reports from ReliefWeb."
        ),
    ),
    execute=execute_get_humanitarian_context_tool,
)
