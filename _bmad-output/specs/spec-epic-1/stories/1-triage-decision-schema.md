---
title: 'Triage decision schema'
type: 'feature'
created: '2026-09-26'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: ['{project-root}/TRIAGE_POLICY.md', '{project-root}/_bmad-output/specs/spec-epic-1/SPEC.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing defines what a triage decision is, so the agent (Epic 2) and the eval (Epic 3) cannot validate or score one.

**Approach:** A pydantic model, `TriageDecision`, in a new root module `schema.py`. It accepts exactly the four fields and rejects anything else with an error that names the offending field.

## Boundaries & Constraints

**Always:** Python 3.12+ with uv; pydantic is already a dependency. Category is one of billing, bug, access, performance, how-to. Priority is one of P1, P2, P3, P4. Route is one of billing-team, bug-team, access-team, performance-team, how-to-team. Rationale is a non-empty string. Route must match the category per `TRIAGE_POLICY.md` (billing→billing-team, bug→bug-team, access→access-team, performance→performance-team, how-to→how-to-team); a mismatched pair is rejected (decided by the human).

**Never:** No network calls, no API keys. Do not touch `seed/`, `mcp/triage_server.py`, `TRIAGE_POLICY.md`, `eval/labelled_tickets.csv`, or the uncommitted `run_agent.py` and `mlflow.db-journal`. Do not build the loader (story 2) or any agent code.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid decision | billing, P2, billing-team, non-empty rationale | Model instance; dumps back to the same JSON | N/A |
| Bad priority | priority `P5` | Rejected | Error names `priority` |
| Bad category or route | category `refund`, or route `sales-team` | Rejected | Error names the field |
| Missing field | no `rationale` | Rejected | Error names `rationale` |
| Mismatched route | category `billing`, route `bug-team` | Rejected | Error names `route` and the expected route |
| Extra field | additional key such as `confidence` | Rejected | Error names the extra key |
| Empty rationale | `""` or whitespace only | Rejected | Error names `rationale` |

</frozen-after-approval>

## Code Map

- `pyproject.toml` -- pydantic>=2.8 and pytest>=8 are already declared; `testpaths = ["tests"]`. No new dependencies.
- `TRIAGE_POLICY.md` -- "Categories and routes" table is the source of the allowed values and the category-to-route pairing. Read-only.
- `run_agent.py` -- imports `triage` from an `agent` module; Epic 2 will import the schema from `schema.py`. Do not edit.
- `mcp/triage_server.py`, `seed/` -- unrelated to this story; read-only.
- `tests/` -- does not exist yet; create it.

## Tasks & Acceptance

**Execution:**
- [ ] `schema.py` -- add `TriageDecision` (pydantic `BaseModel`, `extra="forbid"`) with `Literal` types for category, priority and route, and a non-empty stripped `rationale`, and a validator enforcing the category-to-route pairing -- single source of truth Epic 2 and 3 import
- [ ] `tests/test_schema.py` -- unit-test every row of the I/O matrix, asserting the failing field is named in the error -- guards the rejection behavior

**Acceptance Criteria:**
- Given a valid decision as a JSON string, when it is validated, then it parses and dumps back to equal JSON.
- Given any invalid input from the matrix, when it is validated, then a `ValidationError` is raised whose message names the offending field.
- `uv run pytest` passes with no network access and no API keys set.

## Implementation Notes

## Spec Change Log

## Review Triage Log

### Review Findings

- [x] [Review][Decision] `pythonpath = ["."]` added to `pyproject.toml`, a file the story does not list — Needed so `from schema import TriageDecision` resolves under pytest (without it, collection fails with `ModuleNotFoundError`). Options: (a) keep it, (b) drop it and use a root `conftest.py` instead. Also depends on pytest running from the repo root. (acceptance-auditor, edge-case-hunter) Resolved: kept (a), no answer given, so the existing setting stands.
- [x] [Review][Patch] Import `Annotated` from `typing`, not `typing_extensions` [schema.py:6] — `typing_extensions` is only a transitive pydantic dependency and `typing.Annotated` exists on Python 3.12. (blind-hunter, edge-case-hunter, acceptance-auditor)
- [x] [Review][Patch] `assert_rejected` matches a substring of the whole message, not the error location [tests/test_schema.py:21] — Assert on `exc.value.errors()` (`loc` and `type`) so a test passes only when the right field is the one that failed. (blind-hunter, acceptance-auditor)
- [x] [Review][Patch] Test gaps [tests/test_schema.py] — Add: `"  x  "` is stored as `"x"`; a mismatch for a category other than billing (e.g. `access` with `billing-team`); each of `category`, `priority` and `route` missing; invalid category plus a route yields only the category error; non-string rationale (`None`, `123`). (blind-hunter, edge-case-hunter, acceptance-auditor)
- [x] [Review][Defer] `mlflow.db-journal` is not covered by `.gitignore` [.gitignore:6] — deferred: pre-existing, outside story 1; `.gitignore` lists `mlflow.db` but not the `-journal` file, so it shows as untracked and could be committed by accident.

#### Rejected

- Mapping can drift from the literals (`KeyError`) — low: the values are fixed by `TRIAGE_POLICY.md`, and the fix adds a consistency check for a change nobody is making.
- Route check depends on field order / use `model_validator` — low: `category` is declared first, and an invalid category is rejected anyway. Checked: an invalid category plus a route gives only the category error.
- No maximum length on `rationale` — the story specifies non-empty only; a cap is a spec change.
- Enum values are case- and whitespace-sensitive — false: the spec says any other value is rejected.
- Round-trip changes a padded rationale — the story asks for a stripped rationale, and resolving it means editing the spec.
- `pydantic` not declared — false: `pyproject.toml` declares `pydantic>=2.8`.
- `schema.py` is a generic module name — false: the story names it.
- `route` duplicates `category`, no docstring — false: required by the story.
- Diff omits `run_agent.py` — false: the story forbids touching it; it is a separate uncommitted edit.
- `uv run pytest` result not shown — false: it ran, 15 passed, API keys unset.

## Design Notes

"One-sentence" rationale is not machine-checkable, so the schema enforces only a non-empty string; the sentence rule stays in `TRIAGE_POLICY.md`'s Output section.

## Verification

**Commands:**
- `uv run pytest` -- expected: all tests pass
