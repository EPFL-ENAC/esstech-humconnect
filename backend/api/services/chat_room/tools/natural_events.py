from api.services.chat_room.tools.base import (
    HumConnectTool,
)
from api.services.natural_events import (
    NaturalEventsContextPull,
    NaturalEventsContextQuery,
)


class NaturalEventsContextInput(NaturalEventsContextQuery):
    pass


def _get_natural_events_context(query: NaturalEventsContextInput) -> str:
    return NaturalEventsContextPull(query).run()


GET_NATURAL_EVENTS_CONTEXT_TOOL = HumConnectTool.from_sync_handler(
    name="get_natural_events_context",
    label="Get natural events context",
    input_model=NaturalEventsContextInput,
    description=(
        "Fetch nearby natural hazard and disaster context from NASA EONET "
        "and the USGS Earthquake Catalog for a center point and radius in km."
    ),
    invalid_input_message="get_natural_events_context received invalid query data",
    handler=_get_natural_events_context,
)
