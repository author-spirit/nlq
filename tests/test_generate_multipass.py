import json

import pytest
from fastapi.testclient import TestClient

from nlq import catalog, generate
from nlq.api import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_pick_adds_fk_neighbours(monkeypatch):
    info = catalog.load("ecommerce", force=True)

    def fake(_messages):
        return json.dumps({"tables": ["order_items"]})

    monkeypatch.setattr(generate, "complete", fake)
    names = generate._pick("line totals", info)
    assert "order_items" in names
    assert "orders" in names or "products" in names


def test_repair_retries_after_bad_sql(client, monkeypatch):
    calls = {"n": 0}

    def fake(messages):
        calls["n"] += 1
        if calls["n"] == 1:
            return json.dumps(
                {
                    "answer_type": "sql",
                    "sql": "SELECT nope FROM missing_table",
                    "tables": [],
                    "title": "Bad",
                    "chart": {"type": "table", "x": "", "y": [], "series": None},
                    "assumptions": [],
                    "reason": None,
                }
            )
        return json.dumps(
            {
                "answer_type": "sql",
                "sql": "SELECT status, count(*) AS orders FROM orders GROUP BY status ORDER BY orders DESC LIMIT 5",
                "tables": [],
                "title": "Fixed",
                "chart": {"type": "bar", "x": "status", "y": ["orders"], "series": None},
                "assumptions": [],
                "reason": None,
            }
        )

    monkeypatch.setattr(generate, "complete", fake)
    monkeypatch.setattr(generate, "PICK_TOKEN_LIMIT", 10**9)
    response = client.post("/ask", json={"question": "orders by status", "database": "ecommerce"})
    body = response.json()
    assert body["error"] is None
    assert body["title"] == "Fixed"
    assert calls["n"] >= 2
    assert body["repair"] >= 1
