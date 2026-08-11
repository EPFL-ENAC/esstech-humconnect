import pycountry
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.services.chat_room.tools.base import HumConnectTool
from api.services.hunger_map import PALESTINIAN_WFP_AREAS, HungerMapService


class HungerMapInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    country: str = Field(
        pattern=r"^(global|[A-Z]{2,3})$",
        description=(
            "Use 'global' for the global WFP headline and all available country "
            "estimates; an uppercase ISO 3166-1 alpha-2 or alpha-3 country code; "
            "or the WFP area code PSG (Gaza) or PSW (West Bank)."
        ),
    )

    @field_validator("country")
    @classmethod
    def validate_country(cls, value: str) -> str:
        if value == "global" or value in PALESTINIAN_WFP_AREAS:
            return value

        country_record = (
            pycountry.countries.get(alpha_2=value)
            if len(value) == 2
            else pycountry.countries.get(alpha_3=value)
        )
        if country_record is None:
            raise ValueError("country must be 'global', an ISO code, or PSG/PSW")
        return value


def _get_hunger_map_context(query: HungerMapInput) -> str:
    service = HungerMapService()
    response = (
        service.get_global_context()
        if query.country == "global"
        else service.get_context_for_country(query.country)
    )
    return response.model_dump_json(indent=2, exclude_none=True)


GET_HUNGER_MAP_CONTEXT_TOOL = HumConnectTool.from_sync_handler(
    name="get_hunger_map_context",
    label="Get HungerMap food insecurity",
    input_model=HungerMapInput,
    description=(
        "Fetch WFP HungerMap LIVE acute food-insecurity estimates. Use an uppercase "
        "ISO alpha-2/alpha-3 or WFP area code for one country, or 'global' for "
        "the WFP global headline and every available country estimate."
    ),
    invalid_input_message="get_hunger_map_context received invalid query data",
    handler=_get_hunger_map_context,
)
