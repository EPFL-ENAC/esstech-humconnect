import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.sql import operators

from api.config import config
from api.models.root_cause_analysis import (
    RootCauseAnalysis,
    RootCauseAnalysisStep,
)
from api.services import root_cause_analysis as rca_service_module
from api.services.chat_room.tools import root_cause_analysis as rca_tool_module
from api.services.chat_room.tools.base import ToolExecutionContext
from api.services.chat_room.tools.root_cause_analysis import (
    CREATE_ANALYSIS_TOOL,
    GET_ANALYSIS_TOOL,
    LIST_ANALYSES_TOOL,
    SAVE_WHY_ANSWER_TOOL,
    SAVE_WHY_QUESTION_TOOL,
    SET_ROOT_CAUSE_TOOL,
    InvalidAnalysisOrderError,
    RootCauseAnalysisService,
    compute_analysis_state,
)
from tests.chat_room_helpers import *  # noqa: F403  (sets env vars, asyncio, TEST_USER_ID, ...)

RCA_CHAT_ID = uuid4()
RCA_SOURCE_MESSAGE_ID = uuid4()


def rca_tool_context() -> ToolExecutionContext:
    return ToolExecutionContext(
        chat_id=RCA_CHAT_ID,
        user_id=TEST_USER_ID,
        source_message_id=RCA_SOURCE_MESSAGE_ID,
    )


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


def _eq_pair(clause):
    left, right = clause.left, clause.right
    if isinstance(right, sa.sql.elements.BindParameter):
        return getattr(left, "key", None), right.value
    if isinstance(left, sa.sql.elements.BindParameter):
        return getattr(right, "key", None), left.value
    return None, None


def _eq_filters(whereclause):
    if whereclause is None:
        return []
    filters = []
    stack = [whereclause]
    while stack:
        clause = stack.pop()
        op = getattr(clause, "operator", None)
        if op is operators.and_ and hasattr(clause, "clauses"):
            stack.extend(clause.clauses)
        elif op is operators.eq:
            key, val = _eq_pair(clause)
            if key is not None:
                filters.append((key, val))
    return filters


class FakeRcaAsyncSession:
    rows: dict = {RootCauseAnalysis: {}, RootCauseAnalysisStep: {}}
    last_query = None
    commit_count = 0
    instances: list = []

    def __init__(self, *args, **kwargs):
        self.local_commits = 0
        self.added = []
        FakeRcaAsyncSession.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, row_id):
        return self.rows[model].get(row_id)

    def add(self, row):
        self.added.append(row)
        if isinstance(row, RootCauseAnalysis):
            self.rows[RootCauseAnalysis][row.id] = row
        elif isinstance(row, RootCauseAnalysisStep):
            self.rows[RootCauseAnalysisStep][row.id] = row

    async def commit(self):
        self.local_commits += 1
        FakeRcaAsyncSession.commit_count += 1

    async def refresh(self, row):
        return None

    async def exec(self, query):
        FakeRcaAsyncSession.last_query = query
        text = str(query)
        if "rootcauseanalysisstep" in text:
            rows = list(self.rows[RootCauseAnalysisStep].values())
            for key, val in _eq_filters(query.whereclause):
                rows = [r for r in rows if getattr(r, key, None) == val]
            rows.sort(key=lambda r: r.position)
            return _FakeResult(rows)
        if "rootcauseanalysis" in text:
            rows = list(self.rows[RootCauseAnalysis].values())
            for key, val in _eq_filters(query.whereclause):
                rows = [r for r in rows if getattr(r, key, None) == val]
            rows.sort(key=lambda r: r.created_at, reverse=True)
            return _FakeResult(rows)
        return _FakeResult([])

    @classmethod
    def reset(cls):
        cls.rows = {RootCauseAnalysis: {}, RootCauseAnalysisStep: {}}
        cls.last_query = None
        cls.commit_count = 0
        cls.instances = []


def _service(*, now=None) -> RootCauseAnalysisService:
    fixed_now = now or datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    return RootCauseAnalysisService(
        session_factory=FakeRcaAsyncSession,
        engine_factory=lambda: object(),
        now_factory=lambda: fixed_now,
    )


def configure_rca_service(monkeypatch, *, now=None) -> None:
    fixed_now = now or datetime(2026, 7, 21, 12, 0, tzinfo=UTC)

    def factory():
        return RootCauseAnalysisService(
            session_factory=FakeRcaAsyncSession,
            engine_factory=lambda: object(),
            now_factory=lambda: fixed_now,
        )

    monkeypatch.setattr(rca_tool_module, "RootCauseAnalysisService", factory)


def _create(service) -> tuple[RootCauseAnalysis, list[RootCauseAnalysisStep]]:
    return _run(
        service.create_analysis(
            problem_statement="API latency spiked 3x",
            chat_id=RCA_CHAT_ID,
            user_id=TEST_USER_ID,
            source_message_id=RCA_SOURCE_MESSAGE_ID,
        )
    )


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# compute_analysis_state (pure)
# ---------------------------------------------------------------------------


def _step(step_type, level=None, position=0):
    return RootCauseAnalysisStep(
        analysis_id=uuid4(),
        step_type=step_type,
        level=level,
        position=position,
        content="x",
    )


def test_state_right_after_problem_statement_expects_first_question():
    steps = [_step("problem_statement", position=1)]
    state = compute_analysis_state(steps, status="in_progress")
    assert state.current_level == 0
    assert state.next_expected == "question"
    assert state.can_ask_next_why is True
    assert state.can_set_root_cause is False
    assert state.is_completed is False


def test_state_with_pending_question_expects_answer():
    steps = [
        _step("problem_statement", position=1),
        _step("question", level=1, position=2),
    ]
    state = compute_analysis_state(steps, status="in_progress")
    assert state.current_level == 1
    assert state.has_pending_question is True
    assert state.next_expected == "answer"
    assert state.can_ask_next_why is False
    assert state.can_set_root_cause is False


def test_state_after_completed_pair_allows_question_or_root_cause():
    steps = [
        _step("problem_statement", position=1),
        _step("question", level=1, position=2),
        _step("answer", level=1, position=3),
    ]
    state = compute_analysis_state(steps, status="in_progress")
    assert state.current_level == 1
    assert state.next_expected == "question_or_root_cause"
    assert state.can_ask_next_why is True
    assert state.can_set_root_cause is True


def test_state_at_max_levels_requires_root_cause():
    steps = [
        _step("problem_statement", position=1),
        *(
            step
            for i in range(1, config.MAX_WHYS + 1)
            for step in (
                _step("question", level=i, position=2 * i),
                _step("answer", level=i, position=2 * i + 1),
            )
        ),
    ]
    state = compute_analysis_state(steps, status="in_progress")
    assert state.current_level == config.MAX_WHYS
    assert state.next_expected == "root_cause"
    assert state.can_ask_next_why is False
    assert state.can_set_root_cause is True


def test_state_completed_blocks_all_writes():
    steps = [
        _step("problem_statement", position=1),
        _step("question", level=1, position=2),
        _step("answer", level=1, position=3),
        _step("root_cause", position=4),
    ]
    state = compute_analysis_state(steps, status="completed")
    assert state.is_completed is True
    assert state.next_expected == "none"
    assert state.can_ask_next_why is False
    assert state.can_set_root_cause is False


# ---------------------------------------------------------------------------
# Service: persistence and ordering
# ---------------------------------------------------------------------------


def test_create_analysis_persists_analysis_and_problem_statement_step():
    FakeRcaAsyncSession.reset()
    service = _service()

    analysis, steps = _create(service)

    [persisted_analysis] = list(FakeRcaAsyncSession.rows[RootCauseAnalysis].values())
    assert persisted_analysis is analysis
    assert persisted_analysis.status == "in_progress"
    assert persisted_analysis.chat_id == RCA_CHAT_ID
    assert persisted_analysis.initiated_by_user_id == TEST_USER_ID
    assert persisted_analysis.source_message_id == RCA_SOURCE_MESSAGE_ID

    [problem_step] = list(FakeRcaAsyncSession.rows[RootCauseAnalysisStep].values())
    assert problem_step.step_type == "problem_statement"
    assert problem_step.level is None
    assert problem_step.position == 1
    assert problem_step.content == "API latency spiked 3x"
    assert problem_step.analysis_id == analysis.id
    assert steps == [problem_step]


def test_save_why_question_assigns_next_level_and_position():
    FakeRcaAsyncSession.reset()
    service = _service()
    analysis, _ = _create(service)

    analysis, steps = _run(
        service.save_why_question(
            analysis_id=analysis.id, user_id=TEST_USER_ID, question="Why latency?"
        )
    )

    question_step = steps[-1]
    assert question_step.step_type == "question"
    assert question_step.level == 1
    assert question_step.position == 2
    assert question_step.content == "Why latency?"
    assert analysis.updated_at == datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def test_save_why_answer_matches_pending_question_level():
    FakeRcaAsyncSession.reset()
    service = _service()
    analysis, _ = _create(service)
    _run(
        service.save_why_question(
            analysis_id=analysis.id, user_id=TEST_USER_ID, question="Why latency?"
        )
    )

    analysis, steps = _run(
        service.save_why_answer(
            analysis_id=analysis.id, user_id=TEST_USER_ID, answer="DB pool exhausted"
        )
    )

    answer_step = steps[-1]
    assert answer_step.step_type == "answer"
    assert answer_step.level == 1
    assert answer_step.position == 3
    assert answer_step.content == "DB pool exhausted"


@pytest.mark.parametrize(
    ("method", "kwargs", "label"),
    [
        (
            "save_why_answer",
            {"answer": "premature"},
            "answer before any question",
        ),
        (
            "set_root_cause",
            {"root_cause": "premature"},
            "root cause before any question",
        ),
    ],
)
def test_service_rejects_out_of_order_writes_before_first_question(
    method, kwargs, label
):
    FakeRcaAsyncSession.reset()
    service = _service()
    analysis, _ = _create(service)

    call = getattr(service, method)
    with pytest.raises(InvalidAnalysisOrderError, match="invalid_order"):
        _run(call(analysis_id=analysis.id, user_id=TEST_USER_ID, **kwargs))
    assert label


def test_service_rejects_consecutive_question_while_answer_pending():
    FakeRcaAsyncSession.reset()
    service = _service()
    analysis, _ = _create(service)
    _run(
        service.save_why_question(
            analysis_id=analysis.id, user_id=TEST_USER_ID, question="q1"
        )
    )

    with pytest.raises(InvalidAnalysisOrderError, match="invalid_order"):
        _run(
            service.save_why_question(
                analysis_id=analysis.id, user_id=TEST_USER_ID, question="q1b"
            )
        )


def test_service_enforces_max_five_levels():
    FakeRcaAsyncSession.reset()
    service = _service()
    analysis, _ = _create(service)

    for i in range(1, config.MAX_WHYS + 1):
        _run(
            service.save_why_question(
                analysis_id=analysis.id, user_id=TEST_USER_ID, question=f"q{i}"
            )
        )
        _run(
            service.save_why_answer(
                analysis_id=analysis.id, user_id=TEST_USER_ID, answer=f"a{i}"
            )
        )

    with pytest.raises(InvalidAnalysisOrderError, match="invalid_order"):
        _run(
            service.save_why_question(
                analysis_id=analysis.id, user_id=TEST_USER_ID, question="q6"
            )
        )

    analysis, steps = _run(
        service.set_root_cause(
            analysis_id=analysis.id, user_id=TEST_USER_ID, root_cause="fix timeout"
        )
    )
    assert analysis.status == "completed"
    assert sum(1 for s in steps if s.step_type == "question") == config.MAX_WHYS
    assert steps[-1].step_type == "root_cause"
    assert steps[-1].level is None


def test_service_rejects_writes_after_completion():
    FakeRcaAsyncSession.reset()
    service = _service()
    analysis, _ = _create(service)
    _run(
        service.save_why_question(
            analysis_id=analysis.id, user_id=TEST_USER_ID, question="q1"
        )
    )
    _run(
        service.save_why_answer(
            analysis_id=analysis.id, user_id=TEST_USER_ID, answer="a1"
        )
    )
    _run(
        service.set_root_cause(
            analysis_id=analysis.id, user_id=TEST_USER_ID, root_cause="done"
        )
    )

    with pytest.raises(InvalidAnalysisOrderError, match="invalid_order"):
        _run(
            service.save_why_question(
                analysis_id=analysis.id, user_id=TEST_USER_ID, question="late"
            )
        )
    with pytest.raises(InvalidAnalysisOrderError, match="invalid_order"):
        _run(
            service.set_root_cause(
                analysis_id=analysis.id, user_id=TEST_USER_ID, root_cause="again"
            )
        )


def test_service_allows_early_root_cause_after_one_pair():
    FakeRcaAsyncSession.reset()
    service = _service()
    analysis, _ = _create(service)
    _run(
        service.save_why_question(
            analysis_id=analysis.id, user_id=TEST_USER_ID, question="q1"
        )
    )
    _run(
        service.save_why_answer(
            analysis_id=analysis.id, user_id=TEST_USER_ID, answer="a1"
        )
    )

    analysis, steps = _run(
        service.set_root_cause(
            analysis_id=analysis.id, user_id=TEST_USER_ID, root_cause="quick fix"
        )
    )
    assert analysis.status == "completed"
    assert sum(1 for s in steps if s.step_type == "question") == 1


def test_service_get_analysis_returns_steps_ordered_by_position():
    FakeRcaAsyncSession.reset()
    service = _service()
    analysis, _ = _create(service)
    _run(
        service.save_why_question(
            analysis_id=analysis.id, user_id=TEST_USER_ID, question="q1"
        )
    )
    _run(
        service.save_why_answer(
            analysis_id=analysis.id, user_id=TEST_USER_ID, answer="a1"
        )
    )
    _run(
        service.save_why_question(
            analysis_id=analysis.id, user_id=TEST_USER_ID, question="q2"
        )
    )

    analysis, steps = _run(
        service.get_analysis(analysis_id=analysis.id, user_id=TEST_USER_ID)
    )
    assert [s.position for s in steps] == [1, 2, 3, 4]
    assert [s.step_type for s in steps] == [
        "problem_statement",
        "question",
        "answer",
        "question",
    ]


def test_service_rejects_access_by_other_user_and_unknown_id():
    FakeRcaAsyncSession.reset()
    service = _service()
    analysis, _ = _create(service)

    with pytest.raises(ValueError, match="Analysis not found"):
        _run(service.get_analysis(analysis_id=analysis.id, user_id=uuid4()))
    with pytest.raises(ValueError, match="Analysis not found"):
        _run(service.get_analysis(analysis_id=uuid4(), user_id=TEST_USER_ID))
    with pytest.raises(ValueError, match="Analysis not found"):
        _run(
            service.save_why_question(
                analysis_id=analysis.id, user_id=uuid4(), question="q"
            )
        )


def test_service_list_analyses_is_user_scoped_filtered_and_ordered():
    FakeRcaAsyncSession.reset()
    service = _service(now=lambda: datetime(2026, 7, 21, 12, 0, tzinfo=UTC))
    first, _ = _create(service)

    service_later = _service(now=lambda: datetime(2026, 7, 22, 12, 0, tzinfo=UTC))
    second, _ = _run(
        service_later.create_analysis(
            problem_statement="second problem",
            chat_id=RCA_CHAT_ID,
            user_id=TEST_USER_ID,
            source_message_id=RCA_SOURCE_MESSAGE_ID,
        )
    )

    # other user's analysis is hidden
    other_user = uuid4()
    _run(
        _service().create_analysis(
            problem_statement="someone else",
            chat_id=RCA_CHAT_ID,
            user_id=other_user,
            source_message_id=RCA_SOURCE_MESSAGE_ID,
        )
    )

    pairs = _run(service.list_analyses(user_id=TEST_USER_ID))
    assert [a.id for a, _ in pairs] == [second.id, first.id]

    in_progress = _run(
        service.list_analyses(user_id=TEST_USER_ID, status="in_progress")
    )
    assert [a.id for a, _ in in_progress] == [second.id, first.id]
    completed = _run(service.list_analyses(user_id=TEST_USER_ID, status="completed"))
    assert completed == []

    query_text = str(FakeRcaAsyncSession.last_query)
    assert "rootcauseanalysis.initiated_by_user_id" in query_text
    assert "rootcauseanalysis.status" in query_text


def test_service_steps_query_scopes_by_analysis_id():
    FakeRcaAsyncSession.reset()
    service = _service()
    analysis, _ = _create(service)
    _run(
        service.save_why_question(
            analysis_id=analysis.id, user_id=TEST_USER_ID, question="q1"
        )
    )

    _run(service.get_analysis(analysis_id=analysis.id, user_id=TEST_USER_ID))
    query_text = str(FakeRcaAsyncSession.last_query)
    assert "rootcauseanalysisstep.analysis_id" in query_text
    assert "ORDER BY" in query_text


# ---------------------------------------------------------------------------
# Tools: end-to-end through HumConnectTool.execute
# ---------------------------------------------------------------------------


def _tool_json(coro):
    return json.loads(asyncio.run(coro))


def test_create_analysis_tool_returns_snapshot_expecting_first_question(monkeypatch):
    FakeRcaAsyncSession.reset()
    configure_rca_service(monkeypatch)

    output = _tool_json(
        CREATE_ANALYSIS_TOOL.execute(
            {"problem_statement": "API latency spiked 3x"}, rca_tool_context()
        )
    )
    analysis = output["analysis"]
    assert analysis["status"] == "in_progress"
    assert analysis["current_level"] == 0
    assert analysis["next_expected"] == "question"
    assert analysis["can_ask_next_why"] is True
    assert analysis["can_set_root_cause"] is False
    assert analysis["questions_and_answers"] == []
    assert analysis["root_cause"] is None
    assert analysis["problem_statement"] == "API latency spiked 3x"
    assert analysis["analysis_id"]


def test_tools_drive_full_five_whys_flow(monkeypatch):
    FakeRcaAsyncSession.reset()
    configure_rca_service(monkeypatch)

    created = _tool_json(
        CREATE_ANALYSIS_TOOL.execute({"problem_statement": "p"}, rca_tool_context())
    )
    analysis_id = created["analysis"]["analysis_id"]

    def ask(args):
        return _tool_json(SAVE_WHY_QUESTION_TOOL.execute(args, rca_tool_context()))

    def answer(args):
        return _tool_json(SAVE_WHY_ANSWER_TOOL.execute(args, rca_tool_context()))

    for i in range(1, config.MAX_WHYS + 1):
        q = ask({"analysis_id": analysis_id, "question": f"q{i}"})
        assert q["analysis"]["current_level"] == i
        assert q["analysis"]["next_expected"] == "answer"
        assert q["analysis"]["questions_and_answers"][-1] == {
            "level": i,
            "question": f"q{i}",
            "answer": None,
        }

        a = answer({"analysis_id": analysis_id, "answer": f"a{i}"})
        assert a["analysis"]["current_level"] == i
        expected_next = "root_cause" if i == config.MAX_WHYS else "question_or_root_cause"
        assert a["analysis"]["next_expected"] == expected_next
        assert a["analysis"]["questions_and_answers"][-1] == {
            "level": i,
            "question": f"q{i}",
            "answer": f"a{i}",
        }

    final = _tool_json(
        SET_ROOT_CAUSE_TOOL.execute(
            {"analysis_id": analysis_id, "root_cause": "fix it"}, rca_tool_context()
        )
    )
    analysis = final["analysis"]
    assert analysis["status"] == "completed"
    assert analysis["next_expected"] == "none"
    assert analysis["root_cause"] == "fix it"
    assert len(analysis["questions_and_answers"]) == config.MAX_WHYS


def test_save_why_answer_tool_rejects_when_no_pending_question(monkeypatch):
    FakeRcaAsyncSession.reset()
    configure_rca_service(monkeypatch)
    created = _tool_json(
        CREATE_ANALYSIS_TOOL.execute({"problem_statement": "p"}, rca_tool_context())
    )
    analysis_id = created["analysis"]["analysis_id"]

    with pytest.raises(InvalidAnalysisOrderError, match="invalid_order"):
        _run(
            SAVE_WHY_ANSWER_TOOL.execute(
                {"analysis_id": analysis_id, "answer": "premature"},
                rca_tool_context(),
            )
        )


def test_get_analysis_tool_reflects_current_state(monkeypatch):
    FakeRcaAsyncSession.reset()
    configure_rca_service(monkeypatch)
    analysis_id = _tool_json(
        CREATE_ANALYSIS_TOOL.execute({"problem_statement": "p"}, rca_tool_context())
    )["analysis"]["analysis_id"]
    _run(
        SAVE_WHY_QUESTION_TOOL.execute(
            {"analysis_id": analysis_id, "question": "q1"}, rca_tool_context()
        )
    )

    output = _tool_json(
        GET_ANALYSIS_TOOL.execute({"analysis_id": analysis_id}, rca_tool_context())
    )
    analysis = output["analysis"]
    assert analysis["current_level"] == 1
    assert analysis["next_expected"] == "answer"
    assert analysis["questions_and_answers"] == [
        {"level": 1, "question": "q1", "answer": None}
    ]


def test_list_analyses_tool_returns_summaries(monkeypatch):
    FakeRcaAsyncSession.reset()
    configure_rca_service(monkeypatch)
    first = _tool_json(
        CREATE_ANALYSIS_TOOL.execute({"problem_statement": "first"}, rca_tool_context())
    )["analysis"]["analysis_id"]
    second = _tool_json(
        CREATE_ANALYSIS_TOOL.execute(
            {"problem_statement": "second"}, rca_tool_context()
        )
    )["analysis"]["analysis_id"]

    output = _tool_json(LIST_ANALYSES_TOOL.execute({}, rca_tool_context()))
    assert output["message"] == "Found 2 analysis(es)."
    summaries = output["analyses"]
    assert [s["analysis_id"] for s in summaries] == [second, first]
    assert all(s["status"] == "in_progress" for s in summaries)
    assert all(s["current_level"] == 0 for s in summaries)

    # other user sees nothing
    other_ctx = ToolExecutionContext(
        chat_id=RCA_CHAT_ID,
        user_id=uuid4(),
        source_message_id=RCA_SOURCE_MESSAGE_ID,
    )
    output = _tool_json(LIST_ANALYSES_TOOL.execute({}, other_ctx))
    assert output["analyses"] == []


def test_set_root_cause_tool_requires_execution_context():
    FakeRcaAsyncSession.reset()
    with pytest.raises(ValueError, match="requires chat execution context"):
        _run(
            SET_ROOT_CAUSE_TOOL.execute(
                {"analysis_id": str(uuid4()), "root_cause": "x"}
            )
        )


def test_tools_reject_invalid_analysis_id_format(monkeypatch):
    FakeRcaAsyncSession.reset()
    configure_rca_service(monkeypatch)
    _tool_json(
        CREATE_ANALYSIS_TOOL.execute({"problem_statement": "p"}, rca_tool_context())
    )
    with pytest.raises(ValueError, match="Invalid analysis_id"):
        _run(
            GET_ANALYSIS_TOOL.execute({"analysis_id": "not-a-uuid"}, rca_tool_context())
        )


@pytest.mark.parametrize(
    "arguments",
    [
        {"problem_statement": "  "},
        {"problem_statement": "p", "unexpected": "field"},
        {},
    ],
)
def test_create_analysis_tool_rejects_invalid_input(arguments):
    with pytest.raises(ValueError, match="invalid input data"):
        _run(CREATE_ANALYSIS_TOOL.execute(arguments, rca_tool_context()))


def test_tool_definitions_are_unique_and_named():
    from api.services.chat_room.tools.root_cause_analysis import (
        ROOT_CAUSE_ANALYSIS_TOOLS,
    )

    names = [tool.name for tool in ROOT_CAUSE_ANALYSIS_TOOLS]
    assert len(names) == len(set(names))
    assert set(names) == {
        "create_analysis",
        "save_why_question",
        "save_why_answer",
        "get_analysis",
        "set_root_cause",
        "list_analyses",
    }
    assert all(
        tool.definition["type"] == "function" for tool in ROOT_CAUSE_ANALYSIS_TOOLS
    )


def test_rca_tools_are_registered_in_default_tool_set():
    from api.services.chat_room.default_tool_set import DEFAULT_LOCAL_TOOLS

    names = {tool.name for tool in DEFAULT_LOCAL_TOOLS}
    assert {
        "create_analysis",
        "save_why_question",
        "save_why_answer",
        "get_analysis",
        "set_root_cause",
        "list_analyses",
    } <= names


def test_rca_service_module_re_exports_invalid_order_error():
    assert rca_service_module.InvalidAnalysisOrderError is InvalidAnalysisOrderError
