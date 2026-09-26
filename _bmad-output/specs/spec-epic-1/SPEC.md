---
id: SPEC-epic-1
companions: [../../../mcp/triage_server.py]
sources: [../../../INTENT.md]
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Epic 1: triage data and schema

## Why

The workshop's triage agent (Epic 2) and its eval (Epic 3) need two things that don't exist yet: a precise definition of what a triage decision is, and the ticket and customer data in a database the MCP server can query. Epic 1 is the vision-layer foundation for attendees building the agent live: without a strict schema, decisions can't be validated or scored; without `app.db`, the agent has nothing to look up.

## Capabilities

- **CAP-1**
  - **intent:** Every triage decision is validated against a fixed schema, so malformed decisions are caught instead of passed downstream.
  - **success:** A JSON object with a category (`billing`, `bug`, `access`, `performance` or `how-to`), a priority (`P1` to `P4`), a route (`billing-team`, `bug-team`, `access-team`, `performance-team` or `how-to-team`) and a one-sentence rationale is accepted. Any other value, a missing field, or an extra shape is rejected with an error that names the offending field.

- **CAP-2**
  - **intent:** One command loads the seed data into a local SQLite database.
  - **success:** `uv run python load_seed.py` creates `app.db` with tables `tickets` and `customers`, each with the same columns as `seed/tickets.csv` and `seed/customers.csv` and one row per CSV data row. Running it a second time leaves the same tables, schema and rows.

## Constraints

- Python 3.12 or newer, managed with uv.
- Every file under `seed/` is read-only; the loader reads it and never writes to it.
- No network calls and no API keys anywhere in this epic.
- `mcp/triage_server.py` already reads `app.db` and stays unchanged: `tickets(ticket_id, customer_id, created_at, text)` and `customers(customer_id, name, plan, open_tickets)` must keep those exact table and column names.

## Non-goals

- The agent, the MCP tools, evals and any user interface (Epics 2 and 3).

## Success signal

After `uv run python load_seed.py`, run twice, `app.db` holds the `tickets` and `customers` tables and `mcp/triage_server.py`'s queries return rows from it. A valid decision passes the schema and an invalid one (for example priority `P5`) fails with a clear error.

## Assumptions

- The schema validates each field's allowed values independently; it does not enforce that a route matches its category (e.g. `billing` with `bug-team`).
- "Clear error" means a validation error naming the field and its allowed values; the exception type and module name are left to implementation.
- "The same database" on a second run means the same schema and table contents, not a byte-identical file.

## Open Questions

- Should the schema reject a decision whose route doesn't match its category, or only validate each field's allowed values?
- Should the loader store `open_tickets` as an integer or as text? The intent only requires the same columns as the CSVs.
