"""Evaluate the triage agent over the labelled tickets with MLflow.

Usage: uv run python eval/run_eval.py
"""

import asyncio
import contextlib
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mlflow  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from mlflow.genai import evaluate, scorer  # noqa: E402
from pydantic import ValidationError  # noqa: E402

import agent  # noqa: E402
from schema import TriageDecision  # noqa: E402

LABELS_PATH = ROOT / "eval" / "labelled_tickets.csv"
TRACKING_URI = "sqlite:///mlflow.db"
EXPERIMENT = "triage-agent"


def load_rows(path: Path = LABELS_PATH) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def build_data(rows: list[dict]) -> list[dict]:
    return [
        {
            "inputs": {"ticket_id": row["ticket_id"]},
            "expectations": {
                "expected_category": row["expected_category"],
                "expected_priority": row["expected_priority"],
                "judge_notes": row["judge_notes"],
            },
        }
        for row in rows
    ]


@contextlib.contextmanager
def auto_approve_escalations():
    """Approve every escalation without asking a person, only while the eval runs."""
    original = agent.ask_human
    approved = {"count": 0}

    async def approve(ticket_id: str, reason: str) -> bool:
        approved["count"] += 1
        return True

    agent.ask_human = approve
    try:
        yield approved
    finally:
        agent.ask_human = original


@mlflow.trace(name="triage_ticket", span_type="AGENT")
def predict(ticket_id: str) -> dict:
    """One ticket, one trace. A failed run becomes an error output so the eval carries on."""
    try:
        return asyncio.run(agent.triage(ticket_id))
    except Exception as error:
        print(f"{ticket_id}: agent run failed: {error}", file=sys.stderr)
        return {"error": str(error)}


def _failed(outputs) -> bool:
    return isinstance(outputs, dict) and "error" in outputs


@scorer
def valid_schema(outputs) -> int:
    try:
        TriageDecision.model_validate(outputs)
    except ValidationError:
        return 0
    return 1


@scorer
def category_match(outputs, expectations) -> int:
    got = outputs.get("category") if isinstance(outputs, dict) else None
    return int(got == expectations["expected_category"])


@scorer
def priority_match(outputs, expectations) -> int:
    got = outputs.get("priority") if isinstance(outputs, dict) else None
    return int(got == expectations["expected_priority"])


@scorer
def tool_order(trace, outputs) -> int:
    if _failed(outputs):
        return 0
    first = {}
    for name in ("get_ticket", "get_customer_history"):
        starts = [span.start_time_ns for span in trace.search_spans(name=name)]
        if not starts:
            return 0
        first[name] = min(starts)
    return int(first["get_ticket"] < first["get_customer_history"])


SCORERS = [valid_schema, category_match, priority_match, tool_order]


def run_eval(rows: list[dict] | None = None, tracking_uri: str = TRACKING_URI):
    """Evaluate the agent over the rows. Returns the MLflow result and the escalations approved."""
    rows = load_rows() if rows is None else rows
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(EXPERIMENT)
    mlflow.langchain.autolog()
    with auto_approve_escalations() as approved:
        result = evaluate(data=build_data(rows), scorers=SCORERS, predict_fn=predict)
    return result, approved["count"]


def main() -> None:
    load_dotenv()
    result, escalations = run_eval()
    print(f"Evaluated the labelled tickets in MLflow run {result.run_id}.")
    print(f"Escalations auto-approved: {escalations}")


if __name__ == "__main__":
    main()
