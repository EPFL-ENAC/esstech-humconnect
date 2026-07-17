from api.config import config
from api.services.chat_room.tools import (
    ASK_MEDITRON_TOOL,
    DUMMY_TOOL,
    GET_HUMANITARIAN_CONTEXT_TOOL,
    GET_NATURAL_EVENTS_CONTEXT_TOOL,
    RECALL_EVENTS_TOOL,
    RECORD_EVENT_TOOL,
    HumConnectMCPProxy,
    ToolSet,
)

DEFAULT_LOCAL_TOOLS = (
    DUMMY_TOOL,
    ASK_MEDITRON_TOOL,
    RECORD_EVENT_TOOL,
    RECALL_EVENTS_TOOL,
    GET_NATURAL_EVENTS_CONTEXT_TOOL,
    GET_HUMANITARIAN_CONTEXT_TOOL,
)

SANIHUB_MCP_PROXY = HumConnectMCPProxy(
    mcp_name="sanihub",
    server_url=config.SANIHUB_MCP_URL,
    timeout_seconds=config.SANIHUB_MCP_TIMEOUT_SECONDS,
    allowed_tools=frozenset({"knowledgeSearch", "getDocumentContent"}),
)

HUMCONNECT_TOOL_SET = ToolSet(
    DEFAULT_LOCAL_TOOLS,
    tool_providers=(SANIHUB_MCP_PROXY,),
)
