import sys
from pathlib import Path

import mlflow
import pytest

import agent

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
import run_eval  # noqa: E402

DECISION = {
    "category": "billing",
    "priority": "P2",
    "route": "billing-team",
    "rationale": "Double charge puts money at stake (P2).",
}
EXPECTED = {"expected_category": "billing", "expected_priority": "P2"}


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A temporary MLflow store, so nothing touches the real mlflow.db."""
    uri = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment("triage-agent")
    return uri


def make_trace(order):
    @mlflow.trace(name="root")
    def root():
        for name in order:
            with mlflow.start_span(name=name):
                pass

    root()
    mlflow.flush_trace_async_logging()
    return mlflow.get_trace(mlflow.get_last_active_trace_id())


# --- the four scorers ------------------------------------------------------------


@pytest.mark.parametrize(
    "outputs,expected",
    [(DECISION, 1), ({**DECISION, "confidence": 0.9}, 0), (None, 0), ({"error": "boom"}, 0)],
)
def test_valid_schema(outputs, expected):
    assert run_eval.valid_schema(outputs=outputs) == expected


@pytest.mark.parametrize(
    "outputs,expected",
    [(DECISION, 1), ({**DECISION, "category": "bug"}, 0), (None, 0), ({"error": "boom"}, 0)],
)
def test_category_match(outputs, expected):
    assert run_eval.category_match(outputs=outputs, expectations=EXPECTED) == expected


@pytest.mark.parametrize(
    "outputs,expected",
    [(DECISION, 1), ({**DECISION, "priority": "P1"}, 0), (None, 0), ({"error": "boom"}, 0)],
)
def test_priority_match(outputs, expected):
    assert run_eval.priority_match(outputs=outputs, expectations=EXPECTED) == expected


@pytest.mark.parametrize(
    "order,expected",
    [
        (["get_ticket", "get_customer_history"], 1),
        (["get_customer_history", "get_ticket"], 0),
        (["get_ticket"], 0),
        (["get_customer_history"], 0),
        ([], 0),
    ],
)
def test_tool_order(store, order, expected):
    assert run_eval.tool_order(trace=make_trace(order), outputs=DECISION) == expected


def test_tool_order_is_zero_when_the_run_failed(store):
    trace = make_trace(["get_ticket", "get_customer_history"])
    assert run_eval.tool_order(trace=trace, outputs={"error": "boom"}) == 0


# --- data and auto-approval --------------------------------------------------------


def test_build_data_uses_every_labelled_row():
    rows = run_eval.load_rows()
    data = run_eval.build_data(rows)
    assert len(data) == 20
    assert data[0]["inputs"] == {"ticket_id": rows[0]["ticket_id"]}
    assert data[0]["expectations"]["expected_category"] == rows[0]["expected_category"]


@pytest.mark.anyio
async def test_auto_approve_never_reads_input_counts_and_restores(monkeypatch):
    def no_input(prompt):
        raise AssertionError("the eval must never wait on terminal input")

    monkeypatch.setattr("builtins.input", no_input)
    original = agent.ask_human
    with run_eval.auto_approve_escalations() as approved:
        assert await agent.ask_human("T-1", "P1 Enterprise") is True
        assert await agent.ask_human("T-2", "P1 Enterprise") is True
    assert approved["count"] == 2
    assert agent.ask_human is original


# --- the whole run, with a stubbed agent -------------------------------------------


def stub_agent(monkeypatch, failing=(), escalating=()):
    rows = {r["ticket_id"]: r for r in run_eval.load_rows()}

    async def triage(ticket_id):
        with mlflow.start_span(name="get_ticket"):
            pass
        with mlflow.start_span(name="get_customer_history"):
            pass
        if ticket_id in failing:
            raise RuntimeError("model unavailable")
        if ticket_id in escalating:
            assert await agent.ask_human(ticket_id, "P1 Enterprise") is True
        row = rows[ticket_id]
        route = {"how-to": "how-to-team"}.get(row["expected_category"], f"{row['expected_category']}-team")
        return {
            "category": row["expected_category"],
            "priority": row["expected_priority"],
            "route": route,
            "rationale": "Stubbed decision.",
        }

    monkeypatch.setattr(agent, "triage", triage)


def test_full_run_logs_one_run_with_all_scorers(store, monkeypatch):
    stub_agent(monkeypatch, escalating=("T-1044", "T-1048"))
    result, escalations = run_eval.run_eval(tracking_uri=store)
    runs = mlflow.search_runs(experiment_names=["triage-agent"])
    assert len(runs) == 1
    for name in ("valid_schema", "category_match", "priority_match", "tool_order"):
        assert result.metrics[f"{name}/mean"] == 1.0
    assert escalations == 2


def test_one_failing_ticket_scores_zero_and_the_rest_still_score(store, monkeypatch):
    stub_agent(monkeypatch, failing=("T-1043",))
    result, _ = run_eval.run_eval(tracking_uri=store)
    for name in ("valid_schema", "category_match", "priority_match", "tool_order"):
        assert result.metrics[f"{name}/mean"] == pytest.approx(19 / 20)


@pytest.mark.anyio
async def test_real_agent_calls_land_in_one_trace_per_ticket(store, monkeypatch, temp_server):
    """The escalation resume is a second agent call; it must stay inside the ticket's trace."""
    from helpers import call, use_model
    from langchain_core.messages import AIMessage

    decision = {**DECISION, "category": "access", "priority": "P1", "route": "access-team"}
    use_model(
        monkeypatch,
        [
            call("get_ticket", {"ticket_id": "T-1"}, "c1"),
            call("get_customer_history", {"customer_id": "C-1"}, "c2"),
            call("escalate_to_human", {"ticket_id": "T-1", "reason": "P1 Enterprise"}, "c3"),
            call("TriageDecision", decision, "c4"),
            AIMessage(content="done"),
        ],
    )
    mlflow.langchain.autolog()
    import anyio

    with run_eval.auto_approve_escalations() as approved:
        output = await anyio.to_thread.run_sync(run_eval.predict, "T-1")
    mlflow.flush_trace_async_logging()
    assert output == decision
    assert approved["count"] == 1
    traces = mlflow.search_traces(locations=[mlflow.get_experiment_by_name("triage-agent").experiment_id], return_type="list")
    assert len(traces) == 1
    assert run_eval.tool_order(trace=traces[0], outputs=output) == 1
