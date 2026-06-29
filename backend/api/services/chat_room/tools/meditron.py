import asyncio

from meditron_mcp.main import ask as ask_meditron

from api.services.chat_room.tools.base import HumConnectTool, ToolExecutionContext


async def execute_ask_meditron_tool(
    arguments: dict[str, object],
    context: ToolExecutionContext | None = None,
) -> str:
    prompt = arguments.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        raise ValueError("ask_meditron requires a non-empty string prompt.")

    system_prompt = arguments.get("system_prompt", "")
    if not isinstance(system_prompt, str):
        raise ValueError("ask_meditron requires system_prompt to be a string.")

    return await asyncio.to_thread(
        ask_meditron,
        prompt=prompt,
        system_prompt=system_prompt,
    )


ASK_MEDITRON_TOOL = HumConnectTool(
    name="ask_meditron",
    label="Ask Meditron",
    definition={
        "type": "function",
        "name": "ask_meditron",
        "description": (
            "Ask Meditron, a medical LLM trained on a curated medical corpus, "
            "for help with medical and clinical questions."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Medical or clinical question to ask Meditron.",
                },
                "system_prompt": {
                    "type": "string",
                    "description": "Optional system instructions for Meditron.",
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
    execute=execute_ask_meditron_tool,
)
