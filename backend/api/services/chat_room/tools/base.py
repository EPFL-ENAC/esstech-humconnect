import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Sequence, cast

from openai.types.responses import (
    FunctionToolParam,
    ResponseFunctionToolCall,
    ResponseInputItemParam,
)

ToolExecutor = Callable[[dict[str, object]], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class HumConnectTool:
    name: str
    label: str
    definition: FunctionToolParam
    execute: ToolExecutor


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
    def __init__(self, tools: Sequence[HumConnectTool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def definitions(self) -> list[FunctionToolParam]:
        return [tool.definition for tool in self._tools.values()]

    def label_for(self, function_call: ResponseFunctionToolCall) -> str:
        tool = self._tools.get(function_call.name)
        return tool.label if tool is not None else function_call.name

    async def execute(
        self, function_call: ResponseFunctionToolCall
    ) -> ToolCallExecution:
        tool_output = await self._execute_tool_call(function_call)
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
        self, function_call: ResponseFunctionToolCall
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
            result = await tool.execute(cast(dict[str, object], arguments))
        except Exception as e:
            return ToolCallOutput.from_failure(str(e))

        return ToolCallOutput.from_success(result)
