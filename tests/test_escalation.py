import pytest
from langchain.tools import tool
from langchain_core.messages import AIMessage

import agent
from helpers import call, use_model

DECISION = {
    "category": "access",
    "priority": "P1",
    "route": "access-team",
    "rationale": "Whole team locked out (P1); Enterprise customer, so escalate.",
}


def escalating_script():
    """The model looks the ticket up, calls escalate_to_human, then answers."""
    return [
        call("get_ticket", {"ticket_id": "T-1"}, "c1"),
        call("get_customer_history", {"customer_id": "C-1"}, "c2"),
        call("escalate_to_human", {"ticket_id": "T-1", "reason": "P1 Enterprise"}, "c3"),
        call("TriageDecision", DECISION, "c4"),
        AIMessage(content="done"),
    ]


@pytest.fixture
def events(monkeypatch):
    """Record, in order, when the human is asked and when the tool really runs."""
    log = []

    @tool
    def escalate_to_human(ticket_id: str, reason: str) -> str:
        """Escalate a ticket to a person."""
        log.append("tool ran")
        return "escalated"

    monkeypatch.setattr(agent, "escalate_to_human", escalate_to_human)
    return log


def answer_with(monkeypatch, events, answer):
    async def fake_ask(ticket_id, reason):
        events.append(f"asked about {ticket_id}")
        return answer

    monkeypatch.setattr(agent, "ask_human", fake_ask)


@pytest.mark.anyio
async def test_approved_runs_tool_once_after_asking(monkeypatch, temp_server, events, capsys):
    use_model(monkeypatch, escalating_script())
    answer_with(monkeypatch, events, True)
    assert await agent.triage("T-1") == DECISION
    assert events == ["asked about T-1", "tool ran"]
    assert "Escalated to a human." in capsys.readouterr().err


@pytest.mark.anyio
async def test_declined_never_runs_tool_and_still_returns_decision(monkeypatch, temp_server, events, capsys):
    use_model(monkeypatch, escalating_script())
    answer_with(monkeypatch, events, False)
    assert await agent.triage("T-1") == DECISION
    assert events == ["asked about T-1"]
    err = capsys.readouterr().err
    assert "Not escalated." in err and "Escalated to a human." not in err


@pytest.mark.anyio
async def test_rule_does_not_fire_no_prompt_no_line(monkeypatch, temp_server, events, capsys):
    use_model(
        monkeypatch,
        [
            call("get_ticket", {"ticket_id": "T-1"}, "c1"),
            call("get_customer_history", {"customer_id": "C-1"}, "c2"),
            call("TriageDecision", {**DECISION, "priority": "P3"}, "c3"),
            AIMessage(content="done"),
        ],
    )
    answer_with(monkeypatch, events, True)
    assert (await agent.triage("T-1"))["priority"] == "P3"
    assert events == []
    assert capsys.readouterr().err == ""


@pytest.mark.anyio
@pytest.mark.parametrize("typed", ["yes", "YES", " y "])
async def test_explicit_yes_counts(monkeypatch, typed):
    monkeypatch.setattr("builtins.input", lambda prompt: typed)
    assert await agent.ask_human("T-1", "P1 Enterprise") is True


@pytest.mark.anyio
@pytest.mark.parametrize("typed", ["", "maybe", "no", "yess", "ok"])
async def test_anything_else_counts_as_no(monkeypatch, typed):
    monkeypatch.setattr("builtins.input", lambda prompt: typed)
    assert await agent.ask_human("T-1", "P1 Enterprise") is False


@pytest.mark.anyio
async def test_closed_stdin_counts_as_no(monkeypatch):
    def closed(prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", closed)
    assert await agent.ask_human("T-1", "P1 Enterprise") is False


@pytest.mark.anyio
async def test_prompt_names_the_ticket(monkeypatch):
    seen = []
    monkeypatch.setattr("builtins.input", lambda prompt: seen.append(prompt) or "no")
    await agent.ask_human("T-1044", "P1 Enterprise")
    assert "T-1044" in seen[0] and "yes/no" in seen[0]


@pytest.mark.anyio
async def test_unclear_answer_through_the_real_prompt_never_runs_tool(monkeypatch, temp_server, events):
    use_model(monkeypatch, escalating_script())
    monkeypatch.setattr("builtins.input", lambda prompt: "hmm")
    assert await agent.triage("T-1") == DECISION
    assert events == []


def test_prompt_tells_the_model_when_to_escalate():
    assert "escalate_to_human" in agent.PROMPT_PREAMBLE
    assert "No escalation tool is available" not in agent.PROMPT_PREAMBLE
