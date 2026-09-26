---
title: 'Human-gated escalation'
type: 'feature'
created: '2026-09-26'
status: 'in-progress'
baseline_commit: 'd3e633c4c53b88554fc9b41f81b4e5042b15cf6a'
route: 'dispatch'
review_loop_iteration: 0
context: ['{project-root}/TRIAGE_POLICY.md', '{project-root}/_bmad-output/specs/spec-epic-2/SPEC.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `TRIAGE_POLICY.md` says to escalate a P1 Enterprise ticket to a person, but the agent has no escalation tool, and nothing stops an agent from escalating on its own.

**Approach:** Add a local `escalate_to_human` tool to `agent.py`, gated by LangChain's `HumanInTheLoopMiddleware`, so every call pauses the run for a terminal yes/no. Only an explicit yes runs the tool. This is CAP-5.

## Boundaries & Constraints

**Always:** The tool lives in `agent.py`, not in `mcp/triage_server.py`. The gate covers `escalate_to_human` on every call, with only `approve` and `reject` allowed (no edit). Anything other than `y` or `yes` (any case), including an empty answer or closed stdin, counts as no. The returned decision stays exactly the Epic 1 schema; whether the run escalated is reported by one line on stderr (`Escalated to a human.` or `Not escalated.`) and is visible in the trace, never as an extra field. The system prompt tells the model to call the tool when the policy's escalation rule fires. Tests make no network calls and need no keys.

**Never:** Do not edit `schema.py`, `mcp/triage_server.py`, `TRIAGE_POLICY.md`, `seed/`, `eval/labelled_tickets.csv`, or the uncommitted `run_agent.py`. Do not add a real external escalation system; the tool only confirms. Do not weaken story 1's provider switch, retry or ticket-as-data rules.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Approved | Agent calls `escalate_to_human`; answer `yes` | Tool runs once; run completes; stderr `Escalated to a human.` | N/A |
| Declined | Agent calls the tool; answer `no` | Tool never runs; run completes with the decision; stderr `Not escalated.` | N/A |
| Unclear answer | Empty, `maybe`, or closed stdin | Treated as no | Tool never runs |
| Rule does not fire | Agent never calls the tool | No prompt; no escalation line | N/A |
| Prompt content | Any pause | Prompt names the ticket and asks for yes/no | N/A |

</frozen-after-approval>

## Code Map

- `agent.py` -- story 1's `_invoke_agent` builds `create_agent(...)`; add the tool, `HumanInTheLoopMiddleware(interrupt_on={"escalate_to_human": {"allowed_decisions": ["approve", "reject"]}})` and `checkpointer=InMemorySaver()` with a per-run `thread_id`. Loop while `result` has `__interrupt__`: ask the human, resume with `Command(resume={"decisions": [...]})`. Verify the interrupt and resume shapes against langchain 1.4.2 and langgraph 1.2.12 before coding.
- `agent.py` `PROMPT_PREAMBLE` -- currently says no escalation tool exists; replace with the rule to call it.
- `tests/test_agent.py` -- `ScriptedModel`, `call()` and the `temp_server` fixture to reuse for a scripted tool call.
- `.claude/skills/langchain-middleware/SKILL.md` -- HITL pattern reference.
- `pyproject.toml` -- `langgraph` is already installed via `langchain`; add nothing.

## Tasks & Acceptance

**Execution:**
- [x] `agent.py` -- `escalate_to_human` tool, HITL gate, interrupt/resume loop, injectable `ask_human` (terminal prompt via `asyncio.to_thread(input)`), stderr status line, updated prompt -- CAP-5
- [x] `tests/test_escalation.py` -- every matrix row with a scripted model, the real MCP server on a temporary database, and a patched `ask_human` -- proves the gate cannot be bypassed offline

**Acceptance Criteria:**
- Given the agent calls `escalate_to_human` and the human answers yes, when the run finishes, then the tool ran exactly once and the decision is returned.
- Given any answer that is not an explicit yes, when the run finishes, then the tool never ran.
- Given the tool is called, when the run reaches it, then it always pauses first; no path runs it unprompted.
- Given no key and no network, when `uv run pytest` runs, then it passes.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

A schema-failure retry (story 1) re-runs the agent, so it can ask the human again; that is accepted. The stderr line is chosen because the Epic 1 schema is read-only and rejects extra fields.

## Verification

**Commands:**
- `uv run pytest` -- expected: all tests pass

**Manual checks (needs a live key; use a P1 Enterprise ticket such as `T-1044`):**
- `uv run python run_agent.py T-1044` pauses with a yes/no prompt; `yes` prints `Escalated to a human.`, `no` prints `Not escalated.`, and the decision JSON prints either way.
