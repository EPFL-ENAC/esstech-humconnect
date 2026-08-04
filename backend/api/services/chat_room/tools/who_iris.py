from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from api.config import config
from api.services.chat_room.tools.base import HumConnectTool
from api.services.who_iris import WhoIrisService
from api.utils.pydantic_types import NonEmptyString


class SearchWhoPublicationsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: NonEmptyString = Field(
        description="Terms describing the WHO publication or health topic to find."
    )
    limit: int = Field(
        default=config.WHO_IRIS_SEARCH_LIMIT,
        ge=1,
        le=10,
        description="Maximum number of publications to return.",
    )


class GetWhoPublicationContentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # OpenAI sends function arguments as JSON strings, so this field must allow
    # Pydantic to convert a canonical UUID string even though the model is strict.
    item_id: UUID = Field(
        strict=False,
        description="WHO IRIS item ID returned by search_who_publications.",
    )


def _search_who_publications(query: SearchWhoPublicationsInput) -> str:
    result = WhoIrisService().search(query.query, query.limit)
    return result.model_dump_json(indent=2)


def _get_who_publication_content(query: GetWhoPublicationContentInput) -> str:
    result = WhoIrisService().get_publication_content(query.item_id)
    return result.model_dump_json(indent=2)


SEARCH_WHO_PUBLICATIONS_TOOL = HumConnectTool.from_sync_handler(
    name="search_who_publications",
    label="Search WHO publications",
    input_model=SearchWhoPublicationsInput,
    description=(
        "Search WHO IRIS for health guidance, recommendations, manuals, research, "
        "and technical publications. Returns publication metadata and item IDs."
    ),
    invalid_input_message="search_who_publications received invalid query data",
    handler=_search_who_publications,
)

GET_WHO_PUBLICATION_CONTENT_TOOL = HumConnectTool.from_sync_handler(
    name="get_who_publication_content",
    label="Get WHO publication content",
    input_model=GetWhoPublicationContentInput,
    description=(
        "Get bounded text excerpts from a WHO IRIS publication when its search "
        "result abstract is insufficient."
    ),
    invalid_input_message="get_who_publication_content received an invalid item ID",
    handler=_get_who_publication_content,
)
