import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol, Sequence, TypeVar, cast
from uuid import UUID

from openai import pydantic_function_tool
from openai.types.responses import (
    FunctionToolParam,
    ResponseFunctionToolCall,
    ResponseInputItemParam,
)
from pydantic import BaseModel, ValidationError

from api.models.user_profile import UserProfilePromptContext

logger = logging.getLogger("uvicorn.error")

ToolInputT = TypeVar("ToolInputT", bound=BaseModel)
SyncToolHandler = Callable[[ToolInputT], str]
SyncContextToolHandler = Callable[[ToolInputT, "ToolExecutionContext"], str]
AsyncToolHandler = Callable[[ToolInputT], Awaitable[str]]
AsyncContextToolHandler = Callable[[ToolInputT, "ToolExecutionContext"], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    chat_id: UUID
    user_id: UUID
    source_message_id: UUID
    user_profile_context: UserProfilePromptContext | None = None


ToolExecutor = Callable[
    [dict[str, object], ToolExecutionContext | None],
    Awaitable[str],
]


@dataclass(frozen=True, slots=True)
class HumConnectTool:
    name: str
    label: str
    definition: FunctionToolParam
    execute: ToolExecutor

    @classmethod
    def from_sync_handler(
        cls,
        *,
        name: str,
        label: str,
        input_model: type[ToolInputT],
        description: str,
        invalid_input_message: str,
        handler: SyncToolHandler[ToolInputT],
        include_validation_details: bool = True,
    ) -> "HumConnectTool":
        async def execute(
            arguments: dict[str, object],
            context: ToolExecutionContext | None = None,
        ) -> str:
            tool_input = validate_tool_input(
                input_model,
                arguments,
                invalid_input_message,
                include_details=include_validation_details,
            )
            return await asyncio.to_thread(handler, tool_input)

        return cls(
            name=name,
            label=label,
            definition=pydantic_response_function_tool(
                input_model,
                name=name,
                description=description,
            ),
            execute=execute,
        )

    @classmethod
    def from_sync_with_context_handler(
        cls,
        *,
        name: str,
        label: str,
        input_model: type[ToolInputT],
        description: str,
        invalid_input_message: str,
        handler: SyncContextToolHandler[ToolInputT],
        include_validation_details: bool = True,
    ) -> "HumConnectTool":
        async def execute(
            arguments: dict[str, object],
            context: ToolExecutionContext | None = None,
        ) -> str:
            tool_input = validate_tool_input(
                input_model,
                arguments,
                invalid_input_message,
                include_details=include_validation_details,
            )
            tool_context = require_tool_context(context, name)
            return await asyncio.to_thread(handler, tool_input, tool_context)

        return cls(
            name=name,
            label=label,
            definition=pydantic_response_function_tool(
                input_model,
                name=name,
                description=description,
            ),
            execute=execute,
        )

    @classmethod
    def from_async_handler(
        cls,
        *,
        name: str,
        label: str,
        input_model: type[ToolInputT],
        description: str,
        invalid_input_message: str,
        handler: AsyncToolHandler[ToolInputT],
        include_validation_details: bool = True,
    ) -> "HumConnectTool":
        async def execute(
            arguments: dict[str, object],
            context: ToolExecutionContext | None = None,
        ) -> str:
            tool_input = validate_tool_input(
                input_model,
                arguments,
                invalid_input_message,
                include_details=include_validation_details,
            )
            return await handler(tool_input)

        return cls(
            name=name,
            label=label,
            definition=pydantic_response_function_tool(
                input_model,
                name=name,
                description=description,
            ),
            execute=execute,
        )

    @classmethod
    def from_async_with_context_handler(
        cls,
        *,
        name: str,
        label: str,
        input_model: type[ToolInputT],
        description: str,
        invalid_input_message: str,
        handler: AsyncContextToolHandler[ToolInputT],
        include_validation_details: bool = True,
    ) -> "HumConnectTool":
        async def execute(
            arguments: dict[str, object],
            context: ToolExecutionContext | None = None,
        ) -> str:
            tool_input = validate_tool_input(
                input_model,
                arguments,
                invalid_input_message,
                include_details=include_validation_details,
            )
            tool_context = require_tool_context(context, name)
            return await handler(tool_input, tool_context)

        return cls(
            name=name,
            label=label,
            definition=pydantic_response_function_tool(
                input_model,
                name=name,
                description=description,
            ),
            execute=execute,
        )


class HumConnectToolProvider(Protocol):
    provider_name: str

    async def load_tools(self) -> Sequence[HumConnectTool]: ...


def pydantic_response_function_tool(
    model: type[BaseModel], *, name: str, description: str
) -> FunctionToolParam:
    chat_tool = pydantic_function_tool(model, name=name, description=description)
    function = chat_tool["function"]
    return cast(
        FunctionToolParam,
        {
            "type": "function",
            "name": function["name"],
            "description": function["description"],
            "strict": function["strict"],
            "parameters": function["parameters"],
        },
    )


def validate_tool_input(
    model: type[ToolInputT],
    arguments: dict[str, object],
    error_prefix: str,
    *,
    include_details: bool = True,
) -> ToolInputT:
    try:
        return model.model_validate(arguments)
    except ValidationError as exc:
        if not include_details:
            raise ValueError(error_prefix) from exc
        raise ValueError(f"{error_prefix}: {exc}") from exc


def require_tool_context(
    context: ToolExecutionContext | None,
    tool_name: str,
) -> ToolExecutionContext:
    if context is None:
        raise ValueError(f"{tool_name} requires chat execution context.")
    return context


@dataclass(frozen=True, slots=True)
class ToolCallExecution:
    label: str
    output: str
    succeeded: bool
    function_call_input_item: ResponseInputItemParam
    function_call_output_input_item: ResponseInputItemParam


@dataclass(frozen=True, slots=True)
class ToolCallOutput:
    ok: bool
    result: str | None = None
    error: str | None = None

    @staticmethod
    def from_success(result: str) -> "ToolCallOutput":
        return ToolCallOutput(ok=True, result=result)

    @staticmethod
    def from_failure(error: str) -> "ToolCallOutput":
        return ToolCallOutput(ok=False, error=error)

    def to_json(self) -> str:
        payload: dict[str, object] = {"ok": self.ok}
        if self.ok:
            payload["result"] = self.result or ""
        else:
            payload["error"] = self.error or "Tool execution failed."
        return json.dumps(payload)

    def is_successful(self) -> bool:
        return self.ok

    def display_content(self) -> str:
        if self.ok:
            return self.result or ""
        return self.error or "Tool execution failed."


@dataclass(frozen=True, slots=True)
class ToolCallInputItem:
    call_id: str
    name: str
    arguments: str
    item_id: str | None = None
    status: str | None = None

    @staticmethod
    def from_function_call(
        function_call: ResponseFunctionToolCall,
    ) -> "ToolCallInputItem":
        return ToolCallInputItem(
            call_id=function_call.call_id,
            name=function_call.name,
            arguments=function_call.arguments,
            item_id=function_call.id,
            status=function_call.status,
        )

    def to_openai_input_item(self) -> ResponseInputItemParam:
        item: dict[str, Any] = {
            "type": "function_call",
            "call_id": self.call_id,
            "name": self.name,
            "arguments": self.arguments,
        }
        if self.item_id is not None:
            item["id"] = self.item_id
        if self.status is not None:
            item["status"] = self.status
        return cast(ResponseInputItemParam, item)


def parse_tool_call_arguments(raw_arguments: str) -> dict[str, Any] | None:
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError:
        return None

    if isinstance(arguments, dict):
        return arguments
    return None


@dataclass(frozen=True, slots=True)
class ToolCallOutputItem:
    call_id: str
    output: str

    @staticmethod
    def from_output(call_id: str, output: str) -> "ToolCallOutputItem":
        return ToolCallOutputItem(call_id=call_id, output=output)

    def to_openai_input_item(self) -> ResponseInputItemParam:
        return {
            "type": "function_call_output",
            "call_id": self.call_id,
            "output": self.output,
        }


class ToolSet:
    def __init__(
        self,
        tools: Sequence[HumConnectTool],
        tool_providers: Sequence[HumConnectToolProvider] = (),
    ) -> None:
        local_tools = self._index_tools(tools)
        self._tool_providers = tuple(tool_providers)
        self._is_ready = not self._tool_providers
        self._initialization_lock = asyncio.Lock()
        self._tools = MappingProxyType(local_tools) if self._is_ready else local_tools

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    @staticmethod
    def _index_tools(tools: Sequence[HumConnectTool]) -> dict[str, HumConnectTool]:
        indexed: dict[str, HumConnectTool] = {}
        for tool in tools:
            if tool.name in indexed:
                raise ValueError(f"Duplicate tool name: {tool.name}")
            indexed[tool.name] = tool
        return indexed

    async def initialize(self) -> None:
        async with self._initialization_lock:
            if self._is_ready:
                return

            results = await asyncio.gather(
                *(provider.load_tools() for provider in self._tool_providers),
                return_exceptions=True,
            )
            tools = dict(self._tools)
            for provider, result in zip(
                self._tool_providers,
                results,
                strict=True,
            ):
                if isinstance(result, BaseException):
                    if not isinstance(result, Exception):
                        raise result
                    logger.error(
                        "Failed to load tools from provider %s; skipping it.",
                        provider.provider_name,
                        exc_info=(type(result), result, result.__traceback__),
                    )
                    continue

                try:
                    provider_tools = self._index_tools(result)
                    duplicate_names = provider_tools.keys() & tools.keys()
                    if duplicate_names:
                        duplicates = ", ".join(sorted(duplicate_names))
                        raise ValueError(f"Duplicate tool names: {duplicates}")
                except Exception:
                    logger.exception(
                        "Invalid tools from provider %s; skipping it.",
                        provider.provider_name,
                    )
                    continue

                tools.update(provider_tools)

            self._tools = MappingProxyType(tools)
            self._is_ready = True

    def _require_ready(self) -> None:
        if not self._is_ready:
            raise RuntimeError("ToolSet must be initialized before use.")

    def definitions(self) -> list[FunctionToolParam]:
        self._require_ready()
        return [tool.definition for tool in self._tools.values()]

    def label_for(self, function_call: ResponseFunctionToolCall) -> str:
        self._require_ready()
        tool = self._tools.get(function_call.name)
        return tool.label if tool is not None else function_call.name

    async def execute(
        self,
        function_call: ResponseFunctionToolCall,
        context: ToolExecutionContext | None = None,
    ) -> ToolCallExecution:
        self._require_ready()
        tool_output = await self._execute_tool_call(function_call, context)
        output = tool_output.to_json()
        input_item = ToolCallInputItem.from_function_call(function_call)
        output_item = ToolCallOutputItem.from_output(function_call.call_id, output)
        return ToolCallExecution(
            label=self.label_for(function_call),
            output=tool_output.display_content(),
            succeeded=tool_output.is_successful(),
            function_call_input_item=input_item.to_openai_input_item(),
            function_call_output_input_item=output_item.to_openai_input_item(),
        )

    async def _execute_tool_call(
        self,
        function_call: ResponseFunctionToolCall,
        context: ToolExecutionContext | None,
    ) -> ToolCallOutput:
        tool = self._tools.get(function_call.name)
        if tool is None:
            return ToolCallOutput.from_failure(
                f"Unknown tool: {function_call.name}",
            )

        try:
            arguments = json.loads(function_call.arguments)
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be a JSON object.")
            result = await tool.execute(cast(dict[str, object], arguments), context)
        except Exception as e:
            return ToolCallOutput.from_failure(str(e))

        return ToolCallOutput.from_success(result)
