import asyncio

from pydantic import ValidationError

from api.services.chat_room.tools.base import (
    HumConnectTool,
    ToolExecutionContext,
    pydantic_response_function_tool,
)
from api.services.natural_events import (
    NaturalEventsContextPull,
    NaturalEventsContextQuery,
)


class NaturalEventsContextInput(NaturalEventsContextQuery):
    pass


def _get_natural_events_context(query: NaturalEventsContextInput) -> str:
    return NaturalEventsContextPull(query).run()


async def execute_get_natural_events_context_tool(
    arguments: dict[str, object],
    context: ToolExecutionContext | None = None,
) -> str:
    try:
        query = NaturalEventsContextInput.model_validate(arguments)
    except ValidationError as e:
        raise ValueError(
            f"get_natural_events_context received invalid query data: {e}"
        ) from e

    return await asyncio.to_thread(_get_natural_events_context, query)


GET_NATURAL_EVENTS_CONTEXT_TOOL = HumConnectTool(
    name="get_natural_events_context",
    label="Get natural events context",
    definition=pydantic_response_function_tool(
        NaturalEventsContextInput,
        name="get_natural_events_context",
        description=(
            "Fetch nearby natural hazard and disaster context from NASA EONET "
            "and the USGS Earthquake Catalog for a center point and radius in km."
        ),
    ),
    execute=execute_get_natural_events_context_tool,
)
