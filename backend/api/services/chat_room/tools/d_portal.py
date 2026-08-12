from api.services.chat_room.tools.base import HumConnectTool
from api.services.d_portal import (
    DPortalService,
    GetIatiActivityInput,
    SearchIatiActivitiesInput,
)


def _search_iati_activities(query: SearchIatiActivitiesInput) -> str:
    result = DPortalService().search(query)
    return result.model_dump_json(indent=2)


def _get_iati_activity(query: GetIatiActivityInput) -> str:
    result = DPortalService().get_activity(query.activity_id)
    return result.model_dump_json(indent=2)


SEARCH_IATI_ACTIVITIES_TOOL = HumConnectTool.from_sync_handler(
    name="search_iati_activities",
    label="Search IATI activities",
    input_model=SearchIatiActivitiesInput,
    description=(
        "Search d-portal for aid, development, and humanitarian activities "
        "published to IATI. Filter by narrative keywords, recipient countries, "
        "OECD DAC sectors, reporting organisations, humanitarian flag, or active "
        "years. Returns compact activity summaries and IATI activity IDs. Omit "
        "unused fields."
    ),
    invalid_input_message="search_iati_activities received invalid query data",
    handler=_search_iati_activities,
)

GET_IATI_ACTIVITY_TOOL = HumConnectTool.from_sync_handler(
    name="get_iati_activity",
    label="Get IATI activity",
    input_model=GetIatiActivityInput,
    description=(
        "Get bounded core details, recipient countries, sectors, participating "
        "organisations, and document references for one IATI activity. Use only "
        "an activity_id returned by search_iati_activities."
    ),
    invalid_input_message="get_iati_activity received an invalid activity ID",
    handler=_get_iati_activity,
)
