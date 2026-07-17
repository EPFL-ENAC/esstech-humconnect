import json
import logging
import re
from collections.abc import Sequence
from typing import Any, cast

from fastmcp import Client
from mcp.types import TextContent, Tool
from openai.types.responses import FunctionToolParam

from api.services.chat_room.tools.base import (
    HumConnectTool,
    ToolExecutionContext,
    ToolExecutor,
)

logger = logging.getLogger("uvicorn.error")

_INVALID_TOOL_NAME_CHARACTER = re.compile(r"[^a-zA-Z0-9_-]")
_MAX_TOOL_NAME_LENGTH = 64


class HumConnectMCPProxy:
    def __init__(
        self,
        *,
        mcp_name: str,
        server_url: str,
        timeout_seconds: float,
        allowed_tools: frozenset[str] | None = None,
    ) -> None:
        if allowed_tools is not None and not allowed_tools:
            raise ValueError("An MCP tool allowlist cannot be empty.")

        self.mcp_name = self._sanitize_name(mcp_name)
        self.server_url = server_url
        self.timeout_seconds = timeout_seconds
        self.allowed_tools = allowed_tools

    @property
    def provider_name(self) -> str:
        return self.mcp_name

    async def load_tools(self) -> Sequence[HumConnectTool]:
        async with Client(
            self.server_url,
            timeout=self.timeout_seconds,
        ) as client:
            remote_tools = await client.list_tools()

        selected_tools = remote_tools
        if self.allowed_tools is not None:
            remote_names = {tool.name for tool in remote_tools}
            missing_names = self.allowed_tools - remote_names
            if missing_names:
                logger.warning(
                    "MCP server %s did not expose allowlisted tools: %s",
                    self.mcp_name,
                    ", ".join(sorted(missing_names)),
                )
            selected_tools = [
                tool for tool in remote_tools if tool.name in self.allowed_tools
            ]

        if not selected_tools:
            raise ValueError(f"MCP server {self.mcp_name!r} exposed no selected tools.")

        return [self._adapt_tool(remote_tool) for remote_tool in selected_tools]

    def _adapt_tool(self, remote_tool: Tool) -> HumConnectTool:
        public_name = self._public_name(remote_tool.name)
        definition = cast(
            FunctionToolParam,
            {
                "type": "function",
                "name": public_name,
                "description": remote_tool.description
                or f"Tool provided by the {self.mcp_name} MCP server.",
                "parameters": remote_tool.inputSchema,
                "strict": False,
            },
        )
        return HumConnectTool(
            name=public_name,
            label=remote_tool.title or remote_tool.name,
            definition=definition,
            execute=self._make_executor(remote_tool.name),
        )

    def _make_executor(self, remote_name: str) -> ToolExecutor:
        async def execute(
            arguments: dict[str, object],
            context: ToolExecutionContext | None = None,
        ) -> str:
            del context
            async with Client(
                self.server_url,
                timeout=self.timeout_seconds,
            ) as client:
                result = await client.call_tool(
                    remote_name,
                    arguments,
                    raise_on_error=True,
                )
            return serialize_mcp_result(result)

        return execute

    def _public_name(self, remote_name: str) -> str:
        public_name = f"{self.mcp_name}_{self._sanitize_name(remote_name)}"
        if len(public_name) > _MAX_TOOL_NAME_LENGTH:
            raise ValueError(
                f"MCP tool name exceeds {_MAX_TOOL_NAME_LENGTH} characters: "
                f"{public_name!r}"
            )
        return public_name

    @staticmethod
    def _sanitize_name(name: str) -> str:
        sanitized = _INVALID_TOOL_NAME_CHARACTER.sub("_", name).strip("_")
        if not sanitized:
            raise ValueError(f"Invalid empty MCP or tool name: {name!r}")
        return sanitized


def serialize_mcp_result(result: Any) -> str:
    structured_content = getattr(result, "structured_content", None)
    if structured_content is not None:
        return json.dumps(structured_content, ensure_ascii=False, default=str)

    content = result.content
    if all(isinstance(block, TextContent) for block in content):
        return "\n".join(block.text for block in content)

    return json.dumps(
        [block.model_dump(mode="json", by_alias=True) for block in content],
        ensure_ascii=False,
        default=str,
    )
