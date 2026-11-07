from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from nlq import app_settings, history
from nlq.api import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_purge_removes_old_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "PATH", tmp_path / "history.sqlite")
    monkeypatch.setattr(app_settings, "PATH", tmp_path / "settings.json")
    app_settings.save({"history_retention_days": 30})

    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(timespec="seconds")
    history.save(
        {
            "question": "old",
            "title": "old",
            "status": "ok",
            "rows": [],
            "columns": [],
        }
    )
    # Rewrite created_at to the past.
    import sqlite3

    with sqlite3.connect(history.PATH) as con:
        con.execute("UPDATE reports SET created_at = ?", (old,))

    history.save(
        {
            "question": "new",
            "title": "new",
            "status": "ok",
            "rows": [],
            "columns": [],
        }
    )
    reports = history.list_reports()
    questions = {item["question"] for item in reports}
    assert "new" in questions
    assert "old" not in questions


def test_settings_app_endpoint(client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "PATH", tmp_path / "settings.json")
    monkeypatch.setattr(history, "PATH", tmp_path / "history.sqlite")
    response = client.post("/settings/app", json={"history_retention_days": 14})
    assert response.status_code == 200
    body = response.json()
    assert body["history_retention_days"] == 14
    loaded = client.get("/settings/app").json()
    assert loaded["history_retention_days"] == 14
