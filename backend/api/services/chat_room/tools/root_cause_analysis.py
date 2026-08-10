"""5 Whys root cause analysis tools.

Provides an LLM agent with tools to run a structured 5 Whys root cause
analysis (RCA): record a problem statement, save complete why question/answer
pairs, and finally record the root cause.

The level of each why step is never passed as input. It is derived from the
analysis state, and the tools enforce the required sequence:

    create(problem) -> (Q1, A1) -> (Q2, A2) -> ... -> (Q5, A5) -> root_cause
                              ^
              (root cause allowed after any completed question/answer pair)

Out-of-order calls are rejected with a descriptive error so the agent can
self-correct. At most MAX_WHYS why levels are allowed.

Each analysis owns an ordered list of analysis steps (problem statement,
questions, answers, root cause); see `api.models.root_cause_analysis`.
"""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.models.root_cause_analysis import (
    MAX_WHYS,
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
    level: int = Field(ge=1, le=MAX_WHYS, description="1-indexed why level.")
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
        le=MAX_WHYS,
        description=(
            "Level of the most recent question/answer pair, or 0 if no "
            "why step has been saved yet."
        ),
    )
    next_expected: NextExpected = Field(
        description=(
            "The single valid next action: why_step, why_step_or_root_cause, "
            "root_cause, or none."
        ),
    )
    can_save_why_step: bool
    can_set_root_cause: bool
    questions_and_answers: list[WhyQuestionAnswer] = []
    root_cause: str | None = None
    created_at: str
    updated_at: str

    def to_tool_response(self, message: str) -> str:
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
        analysis_id=analysis.analysis_id,
        problem_statement=(
            problem_statement_step.content if problem_statement_step else ""
        ),
        status=analysis.status,
        current_level=state.current_level,
        next_expected=state.next_expected,
        can_save_why_step=state.can_save_why_step,
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


class SaveWhyStepInput(RootCauseAnalysisBaseModel):
    analysis_id: NonEmptyString = Field(
        description="Short mnemonic identifier of the analysis session (e.g. 'rca-1'). Unique within the current chat."
    )
    question: NonEmptyString = Field(
        description=("The 'why' question for current level.")
    )
    answer: NonEmptyString = Field(
        description=(
            "The cause identified at the current level, stated by the user or another tool call. "
            "Provide the answer that corresponds to the question in the same call."
        )
    )


class GetAnalysisInput(RootCauseAnalysisBaseModel):
    analysis_id: NonEmptyString = Field(
        description="Short mnemonic identifier of the analysis session (e.g. 'rca-1'). Unique within the current chat."
    )


class SetRootCauseInput(RootCauseAnalysisBaseModel):
    analysis_id: NonEmptyString = Field(
        description="Short mnemonic identifier of the analysis session (e.g. 'rca-1'). Unique within the current chat."
    )
    root_cause: NonEmptyString = Field(
        description=(
            "The final root cause statement. "
            "Must be set after any completed question/answer pair once the "
            "fundamental cause is clear or if the user wants to, before or at 5 levels."
        )
    )


class ListAnalysesInput(RootCauseAnalysisBaseModel):
    status: AnalysisStatusFilter | None = Field(
        default=None,
        description=(
            "Optional filter: 'in_progress' or 'completed'. Omit to list all."
        ),
    )


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
        f"Created analysis {snapshot.analysis_id}; save the first why step (level 1)."
    )


async def _save_why_step(
    tool_input: SaveWhyStepInput,
    tool_context: ToolExecutionContext,
) -> str:
    analysis, steps = await RootCauseAnalysisService().save_why_step(
        analysis_id=tool_input.analysis_id,
        chat_id=tool_context.chat_id,
        question=tool_input.question,
        answer=tool_input.answer,
    )
    snapshot = build_snapshot(analysis, steps)
    return snapshot.to_tool_response(
        f"Saved why step for level {snapshot.current_level}."
    )


async def _get_analysis(
    tool_input: GetAnalysisInput,
    tool_context: ToolExecutionContext,
) -> str:
    analysis, steps = await RootCauseAnalysisService().get_analysis(
        analysis_id=tool_input.analysis_id,
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
        analysis_id=tool_input.analysis_id,
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
    pairs = await RootCauseAnalysisService().list_analyses(
        chat_id=tool_context.chat_id,
        status=tool_input.status,
    )
    summaries = [
        {
            "analysis_id": analysis.analysis_id,
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


START_5_WHYS_ANALYSIS_TOOL_DESCRIPTION = (
    "Use this tool to start a 5 Whys root cause analysis by recording the problem statement. "
    "Returns a short mnemonic analysis_id (e.g. 'rca-1') that is unique within the current chat. "
    "Keep this analysis_id internal and don't disclose it to the user. "
    "For each level, Formulate a SINGLE clarifying question to understand why the problem statement "
    "occurred (for level 1), or why the previous answer occurred, and either ask this question "
    "to the user, or use a tool call to get an answer. The question can be open-ended or multiple-choice, "
    "but it must be a SINGLE question. "
    "It must not be the same as the problem statement or any previous question. "
    "Save both the clarifying 'why' question and its answer together using the "
    "save_why_step tool. Loop with save_why_step until the root cause is clear, "
    "and finish by calling the set_root_cause tool (allowed before reaching 5 levels). "
    "Use get_analysis to check the current state of an analysis. "
    "Don't call start_5_whys_analysis again if the analysis is already in progress. "
)

SAVE_WHY_STEP_TOOL_DESCRIPTION = (
    "Save one complete 'why' level by recording both the question and its answer. "
    "Each why level must be saved in a separate call. "
    "The question must come from you. The answer can come from the user or from another tool call. "
    "No need to disclose to the user that you are saving the why step. "
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


START_5_WHYS_ANALYSIS_TOOL = HumConnectTool.from_async_with_context_handler(
    name="start_5_whys_analysis",
    label="Start 5 Whys analysis",
    input_model=CreateAnalysisInput,
    description=START_5_WHYS_ANALYSIS_TOOL_DESCRIPTION,
    invalid_input_message="start_5_whys_analysis received invalid input data",
    handler=_create_analysis,
)

SAVE_WHY_STEP_TOOL = HumConnectTool.from_async_with_context_handler(
    name="save_why_step",
    label="Save why step",
    input_model=SaveWhyStepInput,
    description=SAVE_WHY_STEP_TOOL_DESCRIPTION,
    invalid_input_message="save_why_step received invalid input data",
    handler=_save_why_step,
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
    START_5_WHYS_ANALYSIS_TOOL,
    SAVE_WHY_STEP_TOOL,
    GET_ANALYSIS_TOOL,
    SET_ROOT_CAUSE_TOOL,
    LIST_ANALYSES_TOOL,
)

__all__ = [
    "GET_ANALYSIS_TOOL",
    "LIST_ANALYSES_TOOL",
    "ROOT_CAUSE_ANALYSIS_TOOLS",
    "SAVE_WHY_STEP_TOOL",
    "SET_ROOT_CAUSE_TOOL",
    "START_5_WHYS_ANALYSIS_TOOL",
    "InvalidAnalysisOrderError",
]
