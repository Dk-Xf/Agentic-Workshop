import shutil
import sqlite3

import pytest

import agent


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("PROVIDER", "MODEL", "GEMINI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def temp_server(tmp_path, monkeypatch):
    """A copy of the MCP server next to a temporary app.db, so no real data is needed."""
    (tmp_path / "mcp").mkdir()
    shutil.copy(agent.SERVER_PATH, tmp_path / "mcp" / "triage_server.py")
    with sqlite3.connect(tmp_path / "app.db") as conn:
        conn.execute("CREATE TABLE tickets (ticket_id, customer_id, created_at, text)")
        conn.execute("CREATE TABLE customers (customer_id, name, plan, open_tickets)")
        conn.execute("INSERT INTO tickets VALUES ('T-1', 'C-1', '2026-09-01', 'Charged twice.')")
        conn.execute("INSERT INTO customers VALUES ('C-1', 'Northwind', 'Enterprise', 2)")
    monkeypatch.setattr(agent, "SERVER_PATH", tmp_path / "mcp" / "triage_server.py")
