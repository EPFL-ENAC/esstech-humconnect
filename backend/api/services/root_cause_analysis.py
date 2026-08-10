from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession

from api.db import get_engine
from api.models.root_cause_analysis import (
    MAX_WHYS,
    AnalysisStatus,
    RootCauseAnalysis,
    RootCauseAnalysisStep,
)
from api.utils.datetime_utils import utc_now

NextExpected = Literal[
    "question",
    "answer",
    "question_or_root_cause",
    "root_cause",
    "none",
]


@dataclass(frozen=True, slots=True)
class AnalysisState:
    """Derived, read-only view of where an analysis is in the 5 Whys sequence."""

    current_level: int
    has_pending_question: bool
    next_expected: NextExpected
    can_ask_next_why: bool
    can_set_root_cause: bool
    is_completed: bool


class InvalidAnalysisOrderError(ValueError):
    """Raised when a 5 Whys operation violates the required step sequence."""


def compute_analysis_state(
    steps: list[RootCauseAnalysisStep],
    *,
    status: str,
) -> AnalysisState:
    """Derive the analysis state from its ordered steps and status.

    The required sequence is:

        problem_statement -> Q1 -> A1 -> ... -> Q5 -> A5 -> root_cause

    A root cause may be recorded after any completed question/answer pair.
    """
    question_steps = [s for s in steps if s.step_type == "question"]
    answer_steps = [s for s in steps if s.step_type == "answer"]
    has_root_cause = any(s.step_type == "root_cause" for s in steps)
    is_completed = status == "completed" or has_root_cause

    current_level = (question_steps[-1].level or 0) if question_steps else 0
    answered_levels = {a.level for a in answer_steps if a.level is not None}
    has_pending_question = bool(question_steps) and (
        question_steps[-1].level not in answered_levels
    )

    if is_completed:
        next_expected: NextExpected = "none"
    elif not question_steps:
        next_expected = "question"
    elif has_pending_question:
        next_expected = "answer"
    elif current_level >= MAX_WHYS:
        next_expected = "root_cause"
    else:
        next_expected = "question_or_root_cause"

    can_ask_next_why = next_expected in ("question", "question_or_root_cause")
    can_set_root_cause = (
        not is_completed and bool(question_steps) and not has_pending_question
    )

    return AnalysisState(
        current_level=current_level,
        has_pending_question=has_pending_question,
        next_expected=next_expected,
        can_ask_next_why=can_ask_next_why,
        can_set_root_cause=can_set_root_cause,
        is_completed=is_completed,
    )


def _order_error(
    reason: str,
    state: AnalysisState,
) -> InvalidAnalysisOrderError:
    message = (
        f"invalid_order: {reason} "
        f"(current_level={state.current_level}, "
        f"next_expected={state.next_expected}, "
        f"can_ask_next_why={state.can_ask_next_why}, "
        f"can_set_root_cause={state.can_set_root_cause})"
    )
    return InvalidAnalysisOrderError(message)


class RootCauseAnalysisService:
    """Persists 5 Whys analyses and enforces the required step order."""

    def __init__(
        self,
        *,
        session_factory: type[AsyncSQLModelSession] = AsyncSQLModelSession,
        engine_factory: Callable[[], AsyncEngine] = get_engine,
        now_factory: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._engine_factory = engine_factory
        self._now_factory = now_factory

    async def create_analysis(
        self,
        *,
        problem_statement: str,
        chat_id: UUID,
        user_id: UUID,
        source_message_id: UUID,
    ) -> tuple[RootCauseAnalysis, list[RootCauseAnalysisStep]]:
        async with self._session_factory(
            self._engine_factory(),
            expire_on_commit=False,
        ) as session:
            analysis = RootCauseAnalysis(
                analysis_id=await self._generate_analysis_id(session, chat_id),
                chat_id=chat_id,
                initiated_by_user_id=user_id,
                source_message_id=source_message_id,
                status="in_progress",
            )
            step = RootCauseAnalysisStep(
                chat_id=analysis.chat_id,
                analysis_id=analysis.analysis_id,
                step_type="problem_statement",
                level=None,
                position=1,
                content=problem_statement,
            )
            session.add(analysis)
            session.add(step)
            await session.commit()
            await session.refresh(analysis)
            await session.refresh(step)

        return analysis, [step]

    async def ask_why_question(
        self,
        *,
        analysis_id: str,
        chat_id: UUID,
        question: str,
    ) -> tuple[RootCauseAnalysis, list[RootCauseAnalysisStep]]:
        async with self._session_factory(
            self._engine_factory(),
            expire_on_commit=False,
        ) as session:
            analysis, steps = await self._load(session, analysis_id, chat_id)
            state = compute_analysis_state(steps, status=analysis.status)
            if not state.can_ask_next_why:
                reason = self._question_rejection_reason(state)
                raise _order_error(reason, state)

            new_level = state.current_level + 1
            step = RootCauseAnalysisStep(
                chat_id=analysis.chat_id,
                analysis_id=analysis.analysis_id,
                step_type="question",
                level=new_level,
                position=len(steps) + 1,
                content=question,
            )
            analysis.updated_at = self._now_factory()
            session.add(step)
            session.add(analysis)
            await session.commit()
            await session.refresh(step)
            await session.refresh(analysis)
            steps.append(step)

        return analysis, steps

    async def save_why_answer(
        self,
        *,
        analysis_id: str,
        chat_id: UUID,
        answer: str,
    ) -> tuple[RootCauseAnalysis, list[RootCauseAnalysisStep]]:
        async with self._session_factory(
            self._engine_factory(),
            expire_on_commit=False,
        ) as session:
            analysis, steps = await self._load(session, analysis_id, chat_id)
            state = compute_analysis_state(steps, status=analysis.status)
            if state.next_expected != "answer":
                reason = self._answer_rejection_reason(state)
                raise _order_error(reason, state)

            pending_level = state.current_level
            step = RootCauseAnalysisStep(
                chat_id=analysis.chat_id,
                analysis_id=analysis.analysis_id,
                step_type="answer",
                level=pending_level,
                position=len(steps) + 1,
                content=answer,
            )
            analysis.updated_at = self._now_factory()
            session.add(step)
            session.add(analysis)
            await session.commit()
            await session.refresh(step)
            await session.refresh(analysis)
            steps.append(step)

        return analysis, steps

    async def set_root_cause(
        self,
        *,
        analysis_id: str,
        chat_id: UUID,
        root_cause: str,
    ) -> tuple[RootCauseAnalysis, list[RootCauseAnalysisStep]]:
        async with self._session_factory(
            self._engine_factory(),
            expire_on_commit=False,
        ) as session:
            analysis, steps = await self._load(session, analysis_id, chat_id)
            state = compute_analysis_state(steps, status=analysis.status)
            if not state.can_set_root_cause:
                reason = self._root_cause_rejection_reason(state)
                raise _order_error(reason, state)

            step = RootCauseAnalysisStep(
                chat_id=analysis.chat_id,
                analysis_id=analysis.analysis_id,
                step_type="root_cause",
                level=None,
                position=len(steps) + 1,
                content=root_cause,
            )
            analysis.status = "completed"
            analysis.updated_at = self._now_factory()
            session.add(step)
            session.add(analysis)
            await session.commit()
            await session.refresh(step)
            await session.refresh(analysis)
            steps.append(step)

        return analysis, steps

    async def get_analysis(
        self,
        *,
        analysis_id: str,
        chat_id: UUID,
    ) -> tuple[RootCauseAnalysis, list[RootCauseAnalysisStep]]:
        async with self._session_factory(
            self._engine_factory(),
            expire_on_commit=False,
        ) as session:
            return await self._load(session, analysis_id, chat_id)

    async def list_analyses(
        self,
        *,
        chat_id: UUID,
        status: AnalysisStatus | None = None,
    ) -> list[tuple[RootCauseAnalysis, list[RootCauseAnalysisStep]]]:
        async with self._session_factory(
            self._engine_factory(),
            expire_on_commit=False,
        ) as session:
            query = (
                select(RootCauseAnalysis)
                .where(RootCauseAnalysis.chat_id == chat_id)
                .order_by(col(RootCauseAnalysis.created_at).desc())
            )
            if status is not None:
                query = query.where(RootCauseAnalysis.status == status)

            result = await session.exec(query)
            analyses = list(result.all())
            return [
                (
                    analysis,
                    await self._load_steps(
                        session, analysis.chat_id, analysis.analysis_id
                    ),
                )
                for analysis in analyses
            ]

    async def _load(
        self,
        session: AsyncSQLModelSession,
        analysis_id: str,
        chat_id: UUID,
    ) -> tuple[RootCauseAnalysis, list[RootCauseAnalysisStep]]:
        query = (
            select(RootCauseAnalysis)
            .where(RootCauseAnalysis.chat_id == chat_id)
            .where(RootCauseAnalysis.analysis_id == analysis_id)
        )
        result = await session.exec(query)
        analysis = result.first()
        if analysis is None:
            raise ValueError(f"Analysis not found: {analysis_id}")
        steps = await self._load_steps(session, analysis.chat_id, analysis.analysis_id)
        return analysis, steps

    async def _load_steps(
        self,
        session: AsyncSQLModelSession,
        chat_id: UUID,
        analysis_id: str,
    ) -> list[RootCauseAnalysisStep]:
        query = (
            select(RootCauseAnalysisStep)
            .where(RootCauseAnalysisStep.chat_id == chat_id)
            .where(RootCauseAnalysisStep.analysis_id == analysis_id)
            .order_by(col(RootCauseAnalysisStep.position))
        )
        result = await session.exec(query)
        return list(result.all())

    @staticmethod
    async def _generate_analysis_id(
        session: AsyncSQLModelSession,
        chat_id: UUID,
    ) -> str:
        """Return a short mnemonic identifier unique within the chat."""
        query = select(RootCauseAnalysis).where(RootCauseAnalysis.chat_id == chat_id)
        result = await session.exec(query)
        existing = {analysis.analysis_id for analysis in result.all()}
        n = 1
        prefix = "rca"
        while f"{prefix}-{n}" in existing:
            n += 1
        return f"{prefix}-{n}"

    @staticmethod
    def _question_rejection_reason(state: AnalysisState) -> str:
        if state.is_completed:
            return "Analysis is already completed."
        if state.has_pending_question:
            return (
                f"Expected an answer for level {state.current_level}, "
                "not a new question."
            )
        if state.current_level >= MAX_WHYS:
            return f"Maximum of {MAX_WHYS} why levels reached; call set_root_cause."
        return "A new question cannot be saved right now."

    @staticmethod
    def _answer_rejection_reason(state: AnalysisState) -> str:
        if state.is_completed:
            return "Analysis is already completed."
        if not state.has_pending_question and state.current_level == 0:
            return "No pending question to answer. Call ask_why_question first."
        if state.current_level >= MAX_WHYS and not state.has_pending_question:
            return f"Maximum of {MAX_WHYS} why levels reached; call set_root_cause."
        return "No pending question to answer. Call ask_why_question next."

    @staticmethod
    def _root_cause_rejection_reason(state: AnalysisState) -> str:
        if state.is_completed:
            return "Analysis is already completed."
        if state.current_level == 0:
            return (
                "Cannot set root cause before completing at least one "
                "question/answer pair."
            )
        if state.has_pending_question:
            return (
                f"Cannot set root cause while the level {state.current_level} "
                "question is unanswered."
            )
        return "Cannot set root cause right now."
