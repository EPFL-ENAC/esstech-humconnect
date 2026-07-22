"""5 Whys root cause analysis tools.

Provides an LLM agent with tools to run a structured 5 Whys root cause
analysis (RCA): record a problem statement, then alternate between saving
"why" questions and their answers, and finally record the root cause.

The level of each question/answer is never passed as input. It is derived
from the analysis state, and the tools enforce the required sequence:

    create(problem) -> Q1 -> A1 -> Q2 -> A2 -> ... -> Q5 -> A5 -> root_cause
                                                      ^
                              (root cause allowed after any completed A_n, n>=1)

Out-of-order calls are rejected with a descriptive error so the agent can
self-correct. At most MAX_WHYS question/answer levels are allowed.

Each analysis owns an ordered list of analysis steps (problem statement,
questions, answers, root cause); see `api.models.root_cause_analysis`.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from api.config import config
from api.models.root_cause_analysis import (
    RootCauseAnalysis,
    RootCauseAnalysisStep,
)
from api.services.chat_room.tools.base import (
    HumConnectTool,
    ToolExecutionContext,
)
from api.services.root_cause_analysis import (
    InvalidAnalysisOrderError,
    NextExpected,
    RootCauseAnalysisService,
    compute_analysis_state,
)
from api.utils.pydantic_types import NonEmptyString

AnalysisStatusFilter = Literal["in_progress", "completed"]


class RootCauseAnalysisBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WhyQuestionAnswer(RootCauseAnalysisBaseModel):
    level: int = Field(ge=1, le=config.MAX_WHYS, description="1-indexed why level.")
    question: NonEmptyString = Field(description="The 'why' question at this level.")
    answer: NonEmptyString | None = Field(
        default=None,
        description="The cause identified at this level, or null while pending.",
    )


class RootCauseAnalysisSnapshot(RootCauseAnalysisBaseModel):
    analysis_id: NonEmptyString
    problem_statement: str
    status: str
    current_level: int = Field(
        ge=0,
        le=config.MAX_WHYS,
        description=(
            "Level of the most recent question/answer pair, or 0 if no "
            "question has been asked yet."
        ),
    )
    next_expected: NextExpected = Field(
        description=(
            "The single valid next action: question, answer, "
            "question_or_root_cause, root_cause, or none."
        ),
    )
    can_ask_next_why: bool
    can_set_root_cause: bool
    questions_and_answers: list[WhyQuestionAnswer] = []
    root_cause: str | None = None
    created_at: str
    updated_at: str

    def to_tool_response(self, message: str) -> str:
        import json

        return json.dumps(
            {"message": message, "analysis": self.model_dump(mode="json")},
            indent=2,
        )


def build_snapshot(
    analysis: RootCauseAnalysis,
    steps: list[RootCauseAnalysisStep],
) -> RootCauseAnalysisSnapshot:
    state = compute_analysis_state(steps, status=analysis.status)

    question_steps = [s for s in steps if s.step_type == "question"]
    answer_steps = [s for s in steps if s.step_type == "answer"]
    problem_statement_step = next(
        (s for s in steps if s.step_type == "problem_statement"),
        None,
    )
    root_cause_step = next(
        (s for s in steps if s.step_type == "root_cause"),
        None,
    )

    questions_and_answers: list[WhyQuestionAnswer] = []
    for question_step in sorted(question_steps, key=lambda s: s.position):
        if question_step.level is None:
            continue
        matching_answer = next(
            (a for a in answer_steps if a.level == question_step.level),
            None,
        )
        questions_and_answers.append(
            WhyQuestionAnswer(
                level=question_step.level,
                question=question_step.content,
                answer=matching_answer.content if matching_answer else None,
            )
        )

    return RootCauseAnalysisSnapshot(
        analysis_id=str(analysis.id),
        problem_statement=(
            problem_statement_step.content if problem_statement_step else ""
        ),
        status=analysis.status,
        current_level=state.current_level,
        next_expected=state.next_expected,
        can_ask_next_why=state.can_ask_next_why,
        can_set_root_cause=state.can_set_root_cause,
        questions_and_answers=questions_and_answers,
        root_cause=root_cause_step.content if root_cause_step else None,
        created_at=analysis.created_at.isoformat(),
        updated_at=analysis.updated_at.isoformat(),
    )


class CreateAnalysisInput(RootCauseAnalysisBaseModel):
    problem_statement: NonEmptyString = Field(
        description=(
            "The problem or incident being investigated, stated clearly and "
            "factually. Starting point of the 5 Whys analysis."
        )
    )


class SaveWhyQuestionInput(RootCauseAnalysisBaseModel):
    analysis_id: NonEmptyString = Field(description="ID of the analysis session.")
    question: NonEmptyString = Field(
        description=(
            "The 'why' question for the next level. It should ask a SINGLE question "
            "to understand why the previous answer occurred, or why the problem "
            "statement occurred (for level 1)."
        )
    )


class SaveWhyAnswerInput(RootCauseAnalysisBaseModel):
    analysis_id: NonEmptyString = Field(description="ID of the analysis session.")
    answer: NonEmptyString = Field(
        description=(
            "The cause identified at the current level, stated by the user or another tool call."
        )
    )


class GetAnalysisInput(RootCauseAnalysisBaseModel):
    analysis_id: NonEmptyString = Field(description="ID of the analysis session.")


class SetRootCauseInput(RootCauseAnalysisBaseModel):
    analysis_id: NonEmptyString = Field(description="ID of the analysis session.")
    root_cause: NonEmptyString = Field(
        description=(
            "The final root cause statement. "
            "Must be set after any completed question/answer pair once the "
            "fundamental cause is clear of if the user wants to, before or at 5 levels."
        )
    )


class ListAnalysesInput(RootCauseAnalysisBaseModel):
    status: AnalysisStatusFilter | None = Field(
        default=None,
        description=(
            "Optional filter: 'in_progress' or 'completed'. Omit to list all."
        ),
    )


def _parse_analysis_id(raw: str) -> UUID:
    try:
        return UUID(raw)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"Invalid analysis_id: {raw!r}") from exc


async def _create_analysis(
    tool_input: CreateAnalysisInput,
    tool_context: ToolExecutionContext,
) -> str:
    analysis, steps = await RootCauseAnalysisService().create_analysis(
        problem_statement=tool_input.problem_statement,
        chat_id=tool_context.chat_id,
        user_id=tool_context.user_id,
        source_message_id=tool_context.source_message_id,
    )
    snapshot = build_snapshot(analysis, steps)
    return snapshot.to_tool_response(
        f"Created analysis {snapshot.analysis_id}; ask the first 'why' (level 1)."
    )


async def _save_why_question(
    tool_input: SaveWhyQuestionInput,
    tool_context: ToolExecutionContext,
) -> str:
    analysis, steps = await RootCauseAnalysisService().save_why_question(
        analysis_id=_parse_analysis_id(tool_input.analysis_id),
        chat_id=tool_context.chat_id,
        question=tool_input.question,
    )
    snapshot = build_snapshot(analysis, steps)
    return snapshot.to_tool_response(
        f"Saved why question for level {snapshot.current_level}."
    )


async def _save_why_answer(
    tool_input: SaveWhyAnswerInput,
    tool_context: ToolExecutionContext,
) -> str:
    analysis, steps = await RootCauseAnalysisService().save_why_answer(
        analysis_id=_parse_analysis_id(tool_input.analysis_id),
        chat_id=tool_context.chat_id,
        answer=tool_input.answer,
    )
    snapshot = build_snapshot(analysis, steps)
    return snapshot.to_tool_response(
        f"Saved why answer for level {snapshot.current_level}."
    )


async def _get_analysis(
    tool_input: GetAnalysisInput,
    tool_context: ToolExecutionContext,
) -> str:
    analysis, steps = await RootCauseAnalysisService().get_analysis(
        analysis_id=_parse_analysis_id(tool_input.analysis_id),
        chat_id=tool_context.chat_id,
    )
    snapshot = build_snapshot(analysis, steps)
    return snapshot.to_tool_response(
        f"Analysis {snapshot.analysis_id} is {snapshot.status}."
    )


async def _set_root_cause(
    tool_input: SetRootCauseInput,
    tool_context: ToolExecutionContext,
) -> str:
    analysis, steps = await RootCauseAnalysisService().set_root_cause(
        analysis_id=_parse_analysis_id(tool_input.analysis_id),
        chat_id=tool_context.chat_id,
        root_cause=tool_input.root_cause,
    )
    snapshot = build_snapshot(analysis, steps)
    return snapshot.to_tool_response(
        f"Completed analysis {snapshot.analysis_id} after "
        f"{snapshot.current_level} level(s)."
    )


async def _list_analyses(
    tool_input: ListAnalysesInput,
    tool_context: ToolExecutionContext,
) -> str:
    import json

    pairs = await RootCauseAnalysisService().list_analyses(
        chat_id=tool_context.chat_id,
        status=tool_input.status,
    )
    summaries = [
        {
            "analysis_id": str(analysis.id),
            "problem_statement": build_snapshot(analysis, steps).problem_statement,
            "status": analysis.status,
            "current_level": build_snapshot(analysis, steps).current_level,
            "created_at": analysis.created_at.isoformat(),
        }
        for analysis, steps in pairs
    ]
    return json.dumps(
        {"message": f"Found {len(summaries)} analysis(es).", "analyses": summaries},
        indent=2,
    )


CREATE_ANALYSIS_TOOL_DESCRIPTION = (
    "Start a 5 Whys root cause analysis by recording the problem statement; "
    "returns an analysis_id. Then, alternate tool calls to save_why_question and "
    "save_why_answer (max 5 levels), "
    "and finish with set_root_cause (allowed before 5 levels). "
    "Use get_analysis to check the current state of an analysis. "
    "Only ask a SINGLE question at a time. Questions should only come from you. "
    "Answers should only come from the user or tool outputs. "
    "Don't call create_analysis again if the analysis is already in progress."
)

SAVE_WHY_QUESTION_TOOL_DESCRIPTION = (
    "Save the next 'why' question. Ask why the previous answer or the "
    "problem statement occurred, with a single question."
)

SAVE_WHY_ANSWER_TOOL_DESCRIPTION = (
    "Save the answer to the current 'why' question; state a concrete cause, "
    "not a symptom."
)

GET_ANALYSIS_TOOL_DESCRIPTION = (
    "Read an analysis's current state: steps, current level, and next expected "
    "action. Call before a write to recall the current analysis state. Only "
    "analyses belonging to the current chat are accessible."
)

SET_ROOT_CAUSE_TOOL_DESCRIPTION = (
    "Record the final root cause and mark the analysis completed."
)

LIST_ANALYSES_TOOL_DESCRIPTION = (
    "List the analyses for the current chat with IDs, statuses, and current "
    "levels. Only analyses belonging to the current chat are returned."
)


CREATE_ANALYSIS_TOOL = HumConnectTool.from_async_with_context_handler(
    name="create_analysis",
    label="Create root cause analysis",
    input_model=CreateAnalysisInput,
    description=CREATE_ANALYSIS_TOOL_DESCRIPTION,
    invalid_input_message="create_analysis received invalid input data",
    handler=_create_analysis,
)

SAVE_WHY_QUESTION_TOOL = HumConnectTool.from_async_with_context_handler(
    name="save_why_question",
    label="Save why question",
    input_model=SaveWhyQuestionInput,
    description=SAVE_WHY_QUESTION_TOOL_DESCRIPTION,
    invalid_input_message="save_why_question received invalid input data",
    handler=_save_why_question,
)

SAVE_WHY_ANSWER_TOOL = HumConnectTool.from_async_with_context_handler(
    name="save_why_answer",
    label="Save why answer",
    input_model=SaveWhyAnswerInput,
    description=SAVE_WHY_ANSWER_TOOL_DESCRIPTION,
    invalid_input_message="save_why_answer received invalid input data",
    handler=_save_why_answer,
)

GET_ANALYSIS_TOOL = HumConnectTool.from_async_with_context_handler(
    name="get_analysis",
    label="Get root cause analysis",
    input_model=GetAnalysisInput,
    description=GET_ANALYSIS_TOOL_DESCRIPTION,
    invalid_input_message="get_analysis received invalid input data",
    handler=_get_analysis,
)

SET_ROOT_CAUSE_TOOL = HumConnectTool.from_async_with_context_handler(
    name="set_root_cause",
    label="Set root cause",
    input_model=SetRootCauseInput,
    description=SET_ROOT_CAUSE_TOOL_DESCRIPTION,
    invalid_input_message="set_root_cause received invalid input data",
    handler=_set_root_cause,
)

LIST_ANALYSES_TOOL = HumConnectTool.from_async_with_context_handler(
    name="list_analyses",
    label="List root cause analyses",
    input_model=ListAnalysesInput,
    description=LIST_ANALYSES_TOOL_DESCRIPTION,
    invalid_input_message="list_analyses received invalid query data",
    handler=_list_analyses,
)

ROOT_CAUSE_ANALYSIS_TOOLS: tuple[HumConnectTool, ...] = (
    CREATE_ANALYSIS_TOOL,
    SAVE_WHY_QUESTION_TOOL,
    SAVE_WHY_ANSWER_TOOL,
    GET_ANALYSIS_TOOL,
    SET_ROOT_CAUSE_TOOL,
    LIST_ANALYSES_TOOL,
)

__all__ = [
    "InvalidAnalysisOrderError",
    "CREATE_ANALYSIS_TOOL",
    "SAVE_WHY_QUESTION_TOOL",
    "SAVE_WHY_ANSWER_TOOL",
    "GET_ANALYSIS_TOOL",
    "SET_ROOT_CAUSE_TOOL",
    "LIST_ANALYSES_TOOL",
    "ROOT_CAUSE_ANALYSIS_TOOLS",
]
