import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nlq import catalog, db, import_dataset, profile, recommend
from nlq.api import app

ROOT = Path(__file__).resolve().parents[1]
PG_DUMP = ROOT / "fixtures" / "garage" / "postgres.sql"
MY_DUMP = ROOT / "fixtures" / "garage" / "mysql.sql"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_import_postgres_and_mysql_dumps(tmp_path, monkeypatch):
    duck_dir = tmp_path / "duckdb"
    duck_dir.mkdir()
    hints_dir = tmp_path / "hints"
    hints_dir.mkdir()
    datasets = tmp_path / "datasets.json"
    datasets.write_text("{}")

    monkeypatch.setattr(import_dataset, "DUCK_DIR", duck_dir)
    monkeypatch.setattr(import_dataset, "DATASETS_PATH", datasets)
    monkeypatch.setattr(db, "DATASETS_PATH", datasets)
    monkeypatch.setattr(db, "HINTS_DIR", hints_dir)
    monkeypatch.setattr(profile, "HINTS_DIR", hints_dir)
    monkeypatch.setattr(catalog, "HINTS_DIR", hints_dir)

    # Keep builtins; register imports into temp paths.
    monkeypatch.setattr(db, "_BUILTIN", {"ecommerce": db.DB_PATH, "demo_scale": db.DEMO_SCALE_PATH})
    db.reload_databases()

    pg_path = import_dataset.import_sql("garage_pg_test", PG_DUMP, label="Garage PG")
    assert pg_path.exists()
    my_path = import_dataset.import_sql("garage_my_test", MY_DUMP, label="Garage My")
    assert my_path.exists()

    registry = json.loads(datasets.read_text())
    assert "garage_pg_test" in registry
    assert "garage_my_test" in registry

    pg_hints = json.loads((hints_dir / "garage_pg_test.json").read_text())
    my_hints = json.loads((hints_dir / "garage_my_test.json").read_text())
    assert "customers" in pg_hints["tables"]
    assert pg_hints["tables"]["customers"]["row_count"] == 5
    assert any(link["status"] == "declared" for link in pg_hints["links"])
    assert any(link["status"] == "declared" for link in my_hints["links"])
    review = [link for link in pg_hints["links"] if link.get("needs_review")]
    assert review
    assert review[0]["foreign_key"] == "customers.preferred_mechanic_id"


def test_profiler_preserves_human_notes(tmp_path, monkeypatch):
    duck_dir = tmp_path / "duckdb"
    duck_dir.mkdir()
    hints_dir = tmp_path / "hints"
    hints_dir.mkdir()
    datasets = tmp_path / "datasets.json"
    datasets.write_text("{}")
    monkeypatch.setattr(import_dataset, "DUCK_DIR", duck_dir)
    monkeypatch.setattr(import_dataset, "DATASETS_PATH", datasets)
    monkeypatch.setattr(db, "DATASETS_PATH", datasets)
    monkeypatch.setattr(db, "HINTS_DIR", hints_dir)
    monkeypatch.setattr(profile, "HINTS_DIR", hints_dir)
    monkeypatch.setattr(db, "_BUILTIN", {"ecommerce": db.DB_PATH, "demo_scale": db.DEMO_SCALE_PATH})
    db.reload_databases()

    import_dataset.import_sql("garage_note", PG_DUMP, label="Garage")
    path = hints_dir / "garage_note.json"
    document = json.loads(path.read_text())
    document["description"] = "Human garage notes"
    document["tables"]["customers"]["description"] = "People who own cars"
    document["tables"]["customers"]["columns"]["city"]["note"] = "Service city"
    path.write_text(json.dumps(document, indent=2))

    refreshed = profile.profile("garage_note")
    assert refreshed["description"] == "Human garage notes"
    assert refreshed["tables"]["customers"]["description"] == "People who own cars"
    assert refreshed["tables"]["customers"]["columns"]["city"]["note"] == "Service city"
    assert refreshed["tables"]["customers"]["row_count"] == 5


def test_catalog_loads_per_dataset_hints():
    info = catalog.load("ecommerce", force=True)
    assert "orders.customer_id -> customers.customer_id" in info.prompt_text
    assert Path(db.HINTS_DIR / "ecommerce.json").exists()


def test_link_confirm_reject_and_catalog_merge(tmp_path, monkeypatch):
    duck_dir = tmp_path / "duckdb"
    duck_dir.mkdir()
    hints_dir = tmp_path / "hints"
    hints_dir.mkdir()
    datasets = tmp_path / "datasets.json"
    datasets.write_text("{}")
    monkeypatch.setattr(import_dataset, "DUCK_DIR", duck_dir)
    monkeypatch.setattr(import_dataset, "DATASETS_PATH", datasets)
    monkeypatch.setattr(db, "DATASETS_PATH", datasets)
    monkeypatch.setattr(db, "HINTS_DIR", hints_dir)
    monkeypatch.setattr(profile, "HINTS_DIR", hints_dir)
    monkeypatch.setattr(catalog, "HINTS_DIR", hints_dir)
    monkeypatch.setattr(db, "_BUILTIN", {"ecommerce": db.DB_PATH, "demo_scale": db.DEMO_SCALE_PATH})
    db.reload_databases()

    import_dataset.import_sql("garage_links", PG_DUMP, label="Garage")
    guessed = next(
        link
        for link in profile.load_hints("garage_links")["links"]
        if link["foreign_key"] == "customers.preferred_mechanic_id"
    )
    profile.update_link(
        "garage_links",
        guessed["primary_key"],
        guessed["foreign_key"],
        "confirmed",
    )
    confirmed = profile.load_hints("garage_links")
    link = next(item for item in confirmed["links"] if item["foreign_key"] == guessed["foreign_key"])
    assert link["status"] == "confirmed"
    assert link["needs_review"] is False

    info = catalog.load("garage_links", force=True)
    assert "customers.preferred_mechanic_id -> mechanics.mechanic_id" in info.prompt_text

    profile.update_link(
        "garage_links",
        guessed["primary_key"],
        guessed["foreign_key"],
        "rejected",
    )
    info = catalog.load("garage_links", force=True)
    assert "customers.preferred_mechanic_id -> mechanics.mechanic_id" not in info.prompt_text


def test_try_runs_recommendation_sql_without_llm(client, monkeypatch):
    items = recommend.load("ecommerce")
    assert items
    called = {"llm": False}

    def boom(_messages):
        called["llm"] = True
        raise AssertionError("LLM should not be called for /try")

    monkeypatch.setattr("nlq.generate.complete", boom)
    item = items[0]
    response = client.post(
        "/try",
        json={"database": "ecommerce", "question": item["question"], "sql": item["sql"]},
    )
    body = response.json()
    assert response.status_code == 200
    assert called["llm"] is False
    assert body["error"] is None
    assert body["answer_type"] == "sql"
    assert body["sql"] == item["sql"]
    assert body["title"] == item["question"]
    assert body["columns"]
    assert body["row_count"] >= 1


def test_try_rejects_unknown_sql(client):
    response = client.post(
        "/try",
        json={
            "database": "ecommerce",
            "question": "sneaky",
            "sql": "SELECT 1 AS n",
        },
    )
    body = response.json()
    assert body["error"]
    assert "stored recommendation" in body["error"].lower() or "recommendation" in body["error"].lower()


def test_mapping_api(client, tmp_path, monkeypatch):
    duck_dir = tmp_path / "duckdb"
    duck_dir.mkdir()
    hints_dir = tmp_path / "hints"
    hints_dir.mkdir()
    datasets = tmp_path / "datasets.json"
    datasets.write_text("{}")
    monkeypatch.setattr(import_dataset, "DUCK_DIR", duck_dir)
    monkeypatch.setattr(import_dataset, "DATASETS_PATH", datasets)
    monkeypatch.setattr(db, "DATASETS_PATH", datasets)
    monkeypatch.setattr(db, "HINTS_DIR", hints_dir)
    monkeypatch.setattr(profile, "HINTS_DIR", hints_dir)
    monkeypatch.setattr(catalog, "HINTS_DIR", hints_dir)
    monkeypatch.setattr(db, "_BUILTIN", {"ecommerce": db.DB_PATH, "demo_scale": db.DEMO_SCALE_PATH})
    db.reload_databases()
    import_dataset.import_sql("garage_api", PG_DUMP, label="Garage API")

    mapped = client.get("/datasets/garage_api/mapping")
    assert mapped.status_code == 200
    payload = mapped.json()
    assert payload["id"] == "garage_api"
    assert payload["links"]
    review = next(link for link in payload["links"] if link.get("needs_review"))
    updated = client.post(
        "/datasets/garage_api/links",
        json={
            "primary_key": review["primary_key"],
            "foreign_key": review["foreign_key"],
            "status": "confirmed",
        },
    )
    assert updated.status_code == 200
    link = next(
        item
        for item in updated.json()["links"]
        if item["foreign_key"] == review["foreign_key"]
    )
    assert link["status"] == "confirmed"


def test_ui_has_bootstrap_icons_and_no_innerhtml():
    html = (ROOT / "static" / "index.html").read_text()
    js = (ROOT / "static" / "app.js").read_text()
    assert "bootstrap-icons" in html
    assert "bi bi-gear" in html
    assert "innerHTML" not in js
    assert 'fetch("/try"' in js or "fetch(\"/try\"" in js
