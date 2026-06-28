from api.services.chat_room.tools.base import HumConnectTool


async def execute_dummy_tool(arguments: dict[str, object]) -> str:
    message = arguments.get("message")
    if not isinstance(message, str) or not message:
        raise ValueError("dummy_tool requires a non-empty string message.")
    return f"Dummy tool received: {message}"


DUMMY_TOOL = HumConnectTool(
    name="dummy_tool",
    label="Dummy tool",
    definition={
        "type": "function",
        "name": "dummy_tool",
        "description": "A deterministic dummy tool for testing tool-call plumbing.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message to echo through the dummy tool.",
                }
            },
            "required": ["message"],
            "additionalProperties": False,
        },
    },
    execute=execute_dummy_tool,
)
