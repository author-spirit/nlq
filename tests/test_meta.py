from fastapi.testclient import TestClient

from nlq.api import app


def test_databases_come_from_real_files():
    client = TestClient(app)
    response = client.get("/databases")
    assert response.status_code == 200
    body = response.json()
    assert body
    by_id = {item["id"]: item for item in body}
    assert "ecommerce" in by_id
    assert by_id["ecommerce"]["label"] == "Online shop"
    assert by_id["ecommerce"]["tables"] >= 1


def test_usage_endpoint():
    client = TestClient(app)
    response = client.get("/usage")
    assert response.status_code == 200
    body = response.json()
    assert "model" in body
    assert "tokens_total" in body
    assert "chart_failures" in body
    assert "asks_by_day" in body
    assert "by_model" in body
    assert "stats" in body
    assert "outcomes" in body
    assert "charts" in body
    assert body["tokens_total"] >= 0


def test_models_endpoint_lists_providers():
    client = TestClient(app)
    response = client.get("/models")
    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body}
    assert {"openai", "gemini", "claude", "locallama"} <= ids
    assert any(item["active"] for item in body)
