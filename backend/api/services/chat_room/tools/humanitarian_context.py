from pydantic import BaseModel, ConfigDict, Field

from api.services.chat_room.tools.base import (
    HumConnectTool,
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


GET_HUMANITARIAN_CONTEXT_TOOL = HumConnectTool.from_sync_handler(
    name="get_humanitarian_context",
    label="Get humanitarian context",
    input_model=HumanitarianContextInput,
    description=(
        "Fetch recent country-level humanitarian, outbreak, public-health, "
        "displacement, conflict, and crisis reports from ReliefWeb."
    ),
    invalid_input_message="get_humanitarian_context received invalid query data",
    handler=_get_humanitarian_context,
)
