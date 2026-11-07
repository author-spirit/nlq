"""Recommendations load from recommendations/{database}.json and can be generated."""

import json

from fastapi.testclient import TestClient

from nlq import recommend
from nlq.api import app


def test_ecommerce_recommendations_execute():
    items = recommend.load("ecommerce")
    assert len(items) == 5
    for item in items:
        assert item["question"]
        assert item["sql"].upper().startswith("SELECT") or item["sql"].upper().startswith("WITH")


def test_recommendations_endpoint():
    client = TestClient(app)
    response = client.get("/recommendations?database=ecommerce")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    assert "question" in body[0]
    assert "sql" in body[0]


def test_ensure_generates_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(recommend, "DIR", tmp_path)
    calls = {"n": 0}

    def fake_complete(messages):
        calls["n"] += 1
        return json.dumps(
            [
                {
                    "question": "How many orders per status?",
                    "sql": "SELECT status, count(*) AS order_count FROM orders GROUP BY status",
                },
                {
                    "question": "Top categories by revenue",
                    "sql": "SELECT p.category, sum(oi.line_total) AS revenue FROM order_items AS oi JOIN products AS p ON p.product_id = oi.product_id GROUP BY p.category",
                },
            ]
        )

    monkeypatch.setattr(recommend.llm, "complete", fake_complete)
    items = recommend.on_dataset_loaded("ecommerce")
    assert calls["n"] == 1
    assert len(items) == 2
    assert (tmp_path / "ecommerce.json").exists()
    again = recommend.ensure("ecommerce")
    assert calls["n"] == 1
    assert again == items
