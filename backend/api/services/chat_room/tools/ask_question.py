from pydantic import BaseModel, ConfigDict, Field

from api.services.chat_room.tools.base import HumConnectTool
from api.utils.pydantic_types import NonEmptyString


class AskQuestionToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    question: NonEmptyString = Field(description="The question to ask the user.")
    possible_answers: list[NonEmptyString] = Field(
        description=(
            "A list of possible answers to offer to the user as choices. "
            "Use an empty list when no specific options should be offered "
            "and the user should answer freely."
        ),
    )


def _execute_ask_question(tool_input: AskQuestionToolInput) -> str:
    """Return the question so it is preserved in the conversation history.

    The answer is collected from the user by the frontend (which replaces the
    normal chat composer with a dedicated answer UI) and is sent back as a
    regular chat message. Returning the question as the tool output keeps the
    exchange in history even though the tool-call loop is interrupted: the
    question is carried over as the assistant message and the user's answer
    arrives as the next message.
    """
    return tool_input.question


ASK_QUESTION_TOOL = HumConnectTool.from_sync_handler(
    name="ask_question",
    label="Ask question",
    input_model=AskQuestionToolInput,
    description=(
        "Ask the user a question and pause the conversation until they answer. "
        "Provide a clear question and, when helpful, a list of possible answers "
        'to let the user pick from. Don\'t include an "Other (please specify)" option, '
        "as this tool will already do it automatically. Pass an empty possible_answers list when "
        "the user should answer freely. Calling this tool ends the current response: "
        "do not call any other tool in the same turn and do not generate "
        "additional text after it. The user's answer arrives as the next chat "
        "message."
    ),
    invalid_input_message="ask_question received invalid question data",
    handler=_execute_ask_question,
    include_validation_details=False,
    terminal=True,
)
