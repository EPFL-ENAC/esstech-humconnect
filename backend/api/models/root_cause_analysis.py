from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, DateTime, ForeignKeyConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel.sql.sqltypes import AutoString

from api.utils.datetime_utils import utc_now

MAX_WHYS: int = 5

RootCauseAnalysisStepType = Literal[
    "problem_statement",
    "question",
    "answer",
    "root_cause",
]

ROOT_CAUSE_ANALYSIS_STEP_TYPES: tuple[RootCauseAnalysisStepType, ...] = (
    "problem_statement",
    "question",
    "answer",
    "root_cause",
)

AnalysisStatus = Literal["in_progress", "completed"]


class RootCauseAnalysis(SQLModel, table=True):
    """A 5 Whys root cause analysis and its ordered list of steps.

    The analysis owns a sequence of `RootCauseAnalysisStep` rows that record
    the problem statement, alternating why questions and answers, and the
    final root cause. The order is enforced by the service layer; the
    `status` column mirrors whether a root cause step has been recorded.
    """

    __tablename__ = "rootcauseanalysis"
    __table_args__ = (
        UniqueConstraint(
            "chat_id",
            "analysis_id",
            name="uq_rootcauseanalysis_chat_analysis_id",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    analysis_id: str = Field(
        sa_column=Column(AutoString, nullable=False, index=True),
        description="Short mnemonic identifier for the analysis, unique within a chat.",
    )
    chat_id: UUID = Field(foreign_key="chatsession.id", index=True)
    initiated_by_user_id: UUID = Field(foreign_key="userprofile.id", index=True)
    source_message_id: UUID = Field(foreign_key="message.id", index=True)
    status: AnalysisStatus = Field(
        default="in_progress",
        sa_column=Column(AutoString, nullable=False, index=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class RootCauseAnalysisStep(SQLModel, table=True):
    """A single step within a root cause analysis.

    `step_type` is one of problem_statement, question, answer, root_cause.
    `level` is the 1-indexed why level (1..MAX_WHYS) for question and answer
    steps, and null for problem_statement and root_cause steps. `position` is
    the 1-indexed insertion order within the analysis and is used to retrieve
    steps in the order they were recorded.

    `chat_id` and `analysis_id` together form the chat-scoped mnemonic
    reference to the parent `RootCauseAnalysis`.
    """

    __tablename__ = "rootcauseanalysisstep"
    __table_args__ = (
        ForeignKeyConstraint(
            ["chat_id", "analysis_id"],
            ["rootcauseanalysis.chat_id", "rootcauseanalysis.analysis_id"],
            name="fk_rootcauseanalysisstep_analysis",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    chat_id: UUID = Field(index=True)
    analysis_id: str = Field(index=True)
    step_type: RootCauseAnalysisStepType = Field(
        sa_column=Column(AutoString, nullable=False, index=True)
    )
    level: int | None = Field(default=None, index=True)
    position: int = Field(index=True)
    content: str
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )


class RootCauseAnalysisStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    analysis_id: str
    step_type: RootCauseAnalysisStepType
    level: int | None
    position: int
    content: str
    created_at: datetime


class RootCauseAnalysisResponse(BaseModel):
    """Analysis row plus its ordered steps. Built explicitly by the service."""

    model_config = ConfigDict(from_attributes=True)

    analysis_id: str
    chat_id: UUID
    initiated_by_user_id: UUID
    source_message_id: UUID
    status: AnalysisStatus
    steps: list[RootCauseAnalysisStepResponse]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_steps(
        cls,
        analysis: "RootCauseAnalysis",
        steps: list["RootCauseAnalysisStep"],
    ) -> "RootCauseAnalysisResponse":
        ordered_steps = sorted(steps, key=lambda s: s.position)
        return cls.model_validate(
            {
                "analysis_id": analysis.analysis_id,
                "chat_id": analysis.chat_id,
                "initiated_by_user_id": analysis.initiated_by_user_id,
                "source_message_id": analysis.source_message_id,
                "status": analysis.status,
                "steps": [
                    {
                        "analysis_id": analysis.analysis_id,
                        "step_type": step.step_type,
                        "level": step.level,
                        "position": step.position,
                        "content": step.content,
                        "created_at": step.created_at,
                    }
                    for step in ordered_steps
                ],
                "created_at": analysis.created_at,
                "updated_at": analysis.updated_at,
            }
        )

    def to_tool_response(self, message: str) -> str:
        from json import dumps

        return dumps(
            {"message": message, "analysis": self.model_dump(mode="json")},
            indent=2,
        )


class ListRootCauseAnalysesResponse(BaseModel):
    analyses: list[RootCauseAnalysisResponse]
