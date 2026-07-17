import asyncio
import json
import logging
import os
from types import SimpleNamespace
from typing import cast

import pytest
from mcp.types import ImageContent, TextContent, Tool
from openai.types.responses import ResponseFunctionToolCall
from openai.types.responses.response_input_item_param import FunctionCallOutput

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("OPENAI_API_URL", "http://test.local")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("MEDITRON_MCP_API_KEY", "test")
os.environ.setdefault("KEYCLOAK_API_ID", "test")
os.environ.setdefault("KEYCLOAK_API_SECRET", "test")

from api.services.chat_room.tools import DUMMY_TOOL, ToolSet
from api.services.chat_room.tools import mcp_proxy as mcp_proxy_module
from api.services.chat_room.tools.base import HumConnectTool
from api.services.chat_room.tools.mcp_proxy import (
    HumConnectMCPProxy,
    serialize_mcp_result,
)


class FakeMCPClient:
    remote_tools: list[Tool] = []
    call_result = SimpleNamespace(structured_content=None, content=[])
    call_error: Exception | None = None
    list_count = 0
    calls: list[tuple[str, dict[str, object], bool]] = []
    instances: list["FakeMCPClient"] = []

    def __init__(self, url: str, *, timeout: float) -> None:
        self.url = url
        self.timeout = timeout
        self.__class__.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def list_tools(self):
        self.__class__.list_count += 1
        return list(self.__class__.remote_tools)

    async def call_tool(self, name, arguments, *, raise_on_error):
        self.__class__.calls.append((name, arguments, raise_on_error))
        if self.__class__.call_error is not None:
            raise self.__class__.call_error
        return self.__class__.call_result

    @classmethod
    def reset(cls) -> None:
        cls.remote_tools = []
        cls.call_result = SimpleNamespace(structured_content=None, content=[])
        cls.call_error = None
        cls.list_count = 0
        cls.calls = []
        cls.instances = []


@pytest.fixture(autouse=True)
def fake_mcp_client(monkeypatch):
    FakeMCPClient.reset()
    monkeypatch.setattr(mcp_proxy_module, "Client", FakeMCPClient)


def make_proxy(**overrides) -> HumConnectMCPProxy:
    options = {
        "mcp_name": "sanihub",
        "server_url": "https://sanihub.example/mcp",
        "timeout_seconds": 12,
        "allowed_tools": frozenset({"knowledgeSearch"}),
    }
    options.update(overrides)
    return HumConnectMCPProxy(**options)


def make_remote_tool(
    name: str,
    *,
    title: str | None = None,
    description: str | None = "Search sanitation knowledge.",
) -> Tool:
    return Tool(
        name=name,
        title=title,
        description=description,
        inputSchema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )


def test_mcp_proxy_loads_allowed_tools_and_forwards_calls(caplog):
    FakeMCPClient.remote_tools = [
        make_remote_tool("knowledgeSearch", title="Search SaniHub"),
        make_remote_tool("notAllowed"),
    ]
    FakeMCPClient.call_result = SimpleNamespace(
        structured_content={"matches": ["result"]},
        content=[],
    )
    proxy = make_proxy(allowed_tools=frozenset({"knowledgeSearch", "missingTool"}))

    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        tools = asyncio.run(proxy.load_tools())

    assert "missingTool" in caplog.text
    assert FakeMCPClient.list_count == 1
    assert len(tools) == 1
    [tool] = tools
    assert tool.name == "sanihub_knowledgeSearch"
    assert tool.label == "Search SaniHub"
    assert tool.definition == {
        "type": "function",
        "name": "sanihub_knowledgeSearch",
        "description": "Search sanitation knowledge.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "strict": False,
    }

    async def execute_tool() -> str:
        return await tool.execute({"query": "latrines"}, None)

    output = asyncio.run(execute_tool())

    assert json.loads(output) == {"matches": ["result"]}
    assert FakeMCPClient.calls == [("knowledgeSearch", {"query": "latrines"}, True)]
    assert all(
        instance.url == "https://sanihub.example/mcp"
        for instance in FakeMCPClient.instances
    )
    assert all(instance.timeout == 12 for instance in FakeMCPClient.instances)


def test_mcp_proxy_without_allowlist_exposes_every_tool():
    FakeMCPClient.remote_tools = [
        make_remote_tool("knowledgeSearch"),
        make_remote_tool("getDocumentContent"),
    ]

    tools = asyncio.run(make_proxy(allowed_tools=None).load_tools())

    assert [tool.name for tool in tools] == [
        "sanihub_knowledgeSearch",
        "sanihub_getDocumentContent",
    ]


def test_mcp_proxy_rejects_empty_and_overlong_names():
    with pytest.raises(ValueError, match="Invalid empty MCP"):
        make_proxy(mcp_name="...")

    with pytest.raises(ValueError, match="allowlist cannot be empty"):
        make_proxy(allowed_tools=frozenset())

    FakeMCPClient.remote_tools = [make_remote_tool("x" * 64)]
    with pytest.raises(ValueError, match="exceeds 64 characters"):
        asyncio.run(make_proxy(allowed_tools=None).load_tools())


def test_tool_set_skips_provider_with_sanitized_name_collision(caplog):
    FakeMCPClient.remote_tools = [
        make_remote_tool("search knowledge"),
        make_remote_tool("search.knowledge"),
    ]
    proxy = make_proxy(allowed_tools=None)
    tool_set = ToolSet([DUMMY_TOOL], tool_providers=(proxy,))

    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        asyncio.run(tool_set.initialize())

    assert tool_set.is_ready is True
    assert [definition["name"] for definition in tool_set.definitions()] == [
        "dummy_tool"
    ]
    assert "Invalid tools from provider sanihub" in caplog.text


def test_tool_set_skips_provider_with_local_name_collision(caplog):
    FakeMCPClient.remote_tools = [make_remote_tool("tool")]
    proxy = make_proxy(
        mcp_name="dummy",
        allowed_tools=None,
    )
    tool_set = ToolSet([DUMMY_TOOL], tool_providers=(proxy,))

    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        asyncio.run(tool_set.initialize())

    assert [definition["name"] for definition in tool_set.definitions()] == [
        "dummy_tool"
    ]
    assert "Duplicate tool names: dummy_tool" in caplog.text


def test_tool_set_initializes_providers_once_and_skips_failures(caplog):
    class Provider:
        def __init__(self, provider_name, result):
            self.provider_name = provider_name
            self.result = result
            self.load_count = 0

        async def load_tools(self):
            self.load_count += 1
            if isinstance(self.result, Exception):
                raise self.result
            return self.result

    working = Provider("working", [])
    failing = Provider("failing", RuntimeError("offline"))
    tool_set = ToolSet(
        [DUMMY_TOOL],
        tool_providers=(working, failing),
    )
    function_call = ResponseFunctionToolCall(
        arguments="{}",
        call_id="call_1",
        name="dummy_tool",
        type="function_call",
    )

    assert tool_set.is_ready is False
    with pytest.raises(RuntimeError, match="must be initialized"):
        tool_set.definitions()
    with pytest.raises(RuntimeError, match="must be initialized"):
        tool_set.label_for(function_call)
    with pytest.raises(RuntimeError, match="must be initialized"):
        asyncio.run(tool_set.execute(function_call))

    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        asyncio.run(tool_set.initialize())
        asyncio.run(tool_set.initialize())

    assert tool_set.is_ready is True
    assert working.load_count == 1
    assert failing.load_count == 1
    assert [definition["name"] for definition in tool_set.definitions()] == [
        "dummy_tool"
    ]
    assert "Failed to load tools from provider failing" in caplog.text


def test_local_only_tool_set_is_immediately_ready():
    tool_set = ToolSet([DUMMY_TOOL])

    assert tool_set.is_ready is True
    assert [definition["name"] for definition in tool_set.definitions()] == [
        "dummy_tool"
    ]


def test_mcp_proxy_failure_uses_existing_tool_error_output():
    FakeMCPClient.remote_tools = [make_remote_tool("knowledgeSearch")]
    proxy = make_proxy()
    tools = asyncio.run(proxy.load_tools())
    FakeMCPClient.call_error = RuntimeError("SaniHub unavailable")
    tool_set = ToolSet(tools)
    function_call = ResponseFunctionToolCall(
        arguments="{}",
        call_id="call_1",
        name="sanihub_knowledgeSearch",
        type="function_call",
    )

    execution = asyncio.run(tool_set.execute(function_call))

    assert execution.succeeded is False
    assert execution.output == "SaniHub unavailable"
    output_item = cast(
        FunctionCallOutput,
        execution.function_call_output_input_item,
    )
    output = output_item["output"]
    assert isinstance(output, str)
    assert json.loads(output) == {
        "ok": False,
        "error": "SaniHub unavailable",
    }


def test_serialize_mcp_result_supports_text_and_mixed_content():
    text_result = SimpleNamespace(
        structured_content=None,
        content=[
            TextContent(type="text", text="first"),
            TextContent(type="text", text="second"),
        ],
    )
    mixed_result = SimpleNamespace(
        structured_content=None,
        content=[
            TextContent(type="text", text="caption"),
            ImageContent(type="image", data="aW1hZ2U=", mimeType="image/png"),
        ],
    )

    assert serialize_mcp_result(text_result) == "first\nsecond"
    assert json.loads(serialize_mcp_result(mixed_result)) == [
        {"type": "text", "text": "caption", "annotations": None, "_meta": None},
        {
            "type": "image",
            "data": "aW1hZ2U=",
            "mimeType": "image/png",
            "annotations": None,
            "_meta": None,
        },
    ]


def test_app_lifespan_initializes_shared_tool_set(monkeypatch):
    from api import main as main_module

    calls = []

    class FakeToolSet:
        async def initialize(self):
            calls.append("tools")

    async def mark_interrupted():
        calls.append("messages")

    async def dispose():
        calls.append("dispose")

    monkeypatch.setattr(main_module, "HUMCONNECT_TOOL_SET", FakeToolSet())
    monkeypatch.setattr(
        main_module,
        "mark_interrupted_messages_on_startup",
        mark_interrupted,
    )
    monkeypatch.setattr(main_module, "dispose_engine", dispose)

    async def run_lifespan():
        async with main_module.app_lifespan(main_module.app):
            calls.append("serve")

    asyncio.run(run_lifespan())

    assert calls == ["tools", "messages", "serve", "dispose"]
