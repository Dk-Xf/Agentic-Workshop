---
title: 'The eval run and the four code scorers'
type: 'feature'
created: '2026-09-26'
status: 'in-review'
baseline_commit: '734d34c86cbb8762c3339ed0185c6673f57e075d'
route: 'dispatch'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/specs/spec-epic-3/SPEC.md', '{project-root}/_bmad-output/specs/spec-epic-2/SPEC.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing measures how well the Epic 2 agent triages, so there is no baseline to compare against.

**Approach:** `eval/run_eval.py` builds inputs from all 20 rows of `eval/labelled_tickets.csv`, drives `agent.triage` through `mlflow.genai.evaluate`, and logs one run to `sqlite:///mlflow.db` under `triage-agent`. Four code scorers (`valid_schema`, `category_match`, `priority_match`, `tool_order`) score every ticket 0 or 1. Every escalation is auto-approved inside the eval only. Covers CAP-1 to CAP-5 and CAP-8; the judge and the report are story 2.

## Boundaries & Constraints

**Always:** Use `mlflow.genai.evaluate`, not a hand-rolled loop. Each ticket's prediction runs inside one MLflow trace, so the escalation resume stays in the same trace as the tool calls. Set up MLflow as `run_agent.py` does (tracking URI `sqlite:///mlflow.db`, experiment `triage-agent`, `mlflow.langchain.autolog()`). Scorers run locally: schema, label and trace data only. Auto-approval replaces `agent.ask_human` for the duration of the eval and restores it afterwards, and counts each approval; the count is printed. A ticket whose agent run errors does not stop the eval: it scores 0 on all four scorers. Tests make no network calls and need no keys.

**Never:** Do not edit `agent.py`, `schema.py`, `eval/labelled_tickets.csv`, `TRIAGE_POLICY.md`, `mcp/triage_server.py`, `seed/`, or the uncommitted `run_agent.py`. Do not build `rationale_judge`, the report file, or token totals (story 2). Never call Groq or read `GEMINI_API_KEY` in this story's scorers. A normal `run_agent.py` invocation must still pause for a person.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Full run | 20 labelled tickets | Exactly one run in `triage-agent`; all four scorers on all 20 rows | N/A |
| `valid_schema` | Output validates / has an extra field / is missing | 1 / 0 / 0 | N/A |
| `category_match`, `priority_match` | Output equals / differs from the label / is missing | 1 / 0 / 0 | N/A |
| `tool_order` | `get_ticket` span starts before `get_customer_history` / the reverse / either absent | 1 / 0 / 0 | N/A |
| Escalation raised | Agent calls `escalate_to_human` | Approved without reading input; count increases; the run does not block | N/A |
| Eval finished | After `run_eval` returns | `agent.ask_human` is the original again | N/A |
| One ticket errors | Agent raises for one ticket | The other tickets still score; this one scores 0 | Error recorded in the trace |

</frozen-after-approval>

## Code Map

- `eval/labelled_tickets.csv` -- `ticket_id, expected_category, expected_priority, expected_tools, judge_notes`; 20 rows; read-only. `expected_tools` is not used here; `tool_order` checks order only.
- `agent.py` -- `async triage(ticket_id) -> dict`; `ask_human(ticket_id, reason) -> bool` is looked up at call time, so replacing `agent.ask_human` auto-approves without touching decision logic. Read-only.
- `run_agent.py` -- MLflow setup to mirror; shows `load_dotenv()` and `mlflow.start_span`. Do not edit.
- `schema.py` -- `TriageDecision` for `valid_schema`; read-only.
- `tests/conftest.py`, `tests/helpers.py` -- reuse `ScriptedModel`, `call`, `temp_server`, `anyio_backend`.
- Installed: mlflow 3.16.1. Check `mlflow.genai.evaluate(data, scorers, predict_fn)`, `@scorer` argument names (`outputs`, `expectations`, `trace`), and how spans are read (`trace.search_spans(name=...)`, `start_time_ns`) before coding. `predict_fn` receives the row's `inputs` as keyword arguments.
- `eval/run_eval.py` -- new. Put the repo root on `sys.path` before importing `agent`, because running `python eval/run_eval.py` puts only `eval/` on the path.

## Tasks & Acceptance

**Execution:**
- [x] `eval/run_eval.py` -- data builder, `@mlflow.trace` predict function, four `@scorer` functions, auto-approval context, `run_eval()` and `main()` -- CAP-1 to CAP-5, CAP-8
- [x] `tests/test_eval.py` -- every matrix row: scorers on hand-made outputs and real spans, and a small end-to-end `evaluate` on a temporary MLflow store with a stubbed agent -- proves it offline

**Acceptance Criteria:**
- Given 20 labelled tickets and a stubbed agent, when `run_eval` runs, then exactly one MLflow run exists with `valid_schema`, `category_match`, `priority_match` and `tool_order` scored on all 20 rows.
- Given the agent raises an escalation, when the eval runs, then it never reads terminal input and reports how many escalations it approved.
- Given no key and no network, when `uv run pytest` runs, then it passes.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

Live check (needs `app.db`, a working `mlflow.db`, and a Gemini key): `uv run python eval/run_eval.py` takes several minutes because each of the 20 tickets makes real model calls.

## Verification

**Commands:**
- `uv run pytest` -- expected: all tests pass
