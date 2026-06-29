from api.services.chat_room.tools.base import HumConnectTool

RECORDED_EVENTS: list[str] = []


async def execute_record_event_tool(arguments: dict[str, object]) -> str:
    event = arguments.get("event")
    if not isinstance(event, str) or not event:
        raise ValueError("record_event requires a non-empty string event.")

    RECORDED_EVENTS.append(event)
    return f"Recorded event #{len(RECORDED_EVENTS)}: {event}"


RECORD_EVENT_TOOL = HumConnectTool(
    name="record_event",
    label="Record event",
    definition={
        "type": "function",
        "name": "record_event",
        "description": (
            "Record a user-provided fact or event in temporary in-memory storage "
            "so it can be remembered later in this backend process."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "event": {
                    "type": "string",
                    "description": (
                        "The fact or event to remember, for example "
                        "'I have 3 kids that cough since yesterday'."
                    ),
                }
            },
            "required": ["event"],
            "additionalProperties": False,
        },
    },
    execute=execute_record_event_tool,
)
