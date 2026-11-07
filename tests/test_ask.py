import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nlq import prompts
from nlq.api import app
from nlq.guard import check_sql
from nlq.runner import run

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_ask_runs_sql(client, monkeypatch):
    def fake(_messages):
        return json.dumps(
            {
                "answer_type": "sql",
                "sql": "SELECT status, count(*) AS orders FROM orders GROUP BY status ORDER BY orders DESC LIMIT 5",
                "tables": [],
                "title": "Orders by status",
                "chart": {"type": "bar", "x": "status", "y": ["orders"], "series": None},
                "assumptions": ["Counted every order."],
                "reason": None,
            }
        )

    monkeypatch.setattr("nlq.generate.complete", fake)
    response = client.post("/ask", json={"question": "How many orders by status?", "database": "ecommerce"})
    body = response.json()
    assert response.status_code == 200
    assert body["error"] is None
    assert body["answer_type"] == "sql"
    assert body["title"] == "Orders by status"
    assert body["columns"] == ["status", "orders"]
    assert body["row_count"] >= 1
    assert body["rows"]
    assert body["chart"]["type"] == "bar"
    assert body["chart"]["x"] == "status"
    saved = client.get("/history").json()
    assert saved[0]["id"] == body["id"]
    opened = client.get(f"/reports/{body['id']}").json()
    assert opened["sql"] == body["sql"]
    assert opened["rows"] == body["rows"]


def test_ask_schema_returns_columns_without_running_sql(client, monkeypatch):
    def fake(_messages):
        return json.dumps(
            {
                "answer_type": "schema",
                "sql": None,
                "tables": ["orders"],
                "title": "Orders columns",
                "chart": None,
                "assumptions": [],
                "reason": None,
            }
        )

    monkeypatch.setattr("nlq.generate.complete", fake)
    response = client.post("/ask", json={"question": "What fields are in orders?"})
    body = response.json()
    assert body["error"] is None
    assert body["sql"] is None
    assert body["rows"] == []
    names = [column["name"] for column in body["columns"]]
    assert "order_id" in names
    assert "total_amount" in names
    assert all("delivered" not in json.dumps(column) for column in body["columns"])


def test_schema_routes(client):
    tables = client.get("/schema").json()
    names = [table["name"] for table in tables]
    assert "orders" in names
    detail = client.get("/schema/orders").json()
    assert detail["columns"][0]["name"] == "order_id"
    assert detail["columns"][0]["key"] == "PK"
    missing = client.get("/schema/nope")
    assert missing.status_code == 404


def test_examples_execute():
    examples = prompts.load_examples()
    assert len(examples) == 5
    for example in examples:
        sql = check_sql(example["sql"])
        result = run(sql)
        assert result["columns"]
        assert result["rows"]


def test_question_is_last_in_the_prompt():
    messages = prompts.messages("How many customers?", "CREATE TABLE customers (customer_id BIGINT);", "duckdb")
    assert messages[0]["role"] == "system"
    assert "How many customers?" not in messages[0]["content"]
    assert messages[-1]["content"].endswith("How many customers?")
    assert messages[0]["content"].count("Question:") == 3


def test_ui_does_not_use_inner_html():
    script = (ROOT / "static" / "app.js").read_text()
    page = (ROOT / "static" / "index.html").read_text()
    assert "innerHTML" not in script
    assert "outerHTML" not in script
    assert "innerHTML" not in page
