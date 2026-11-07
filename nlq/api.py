"""FastAPI app. Run with: uvicorn nlq.api:app"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from nlq import (
    app_settings,
    catalog,
    charts,
    db,
    errors,
    generate,
    history,
    llm,
    profile,
    recommend,
    runner,
)
from nlq.llm import LLMError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
nlq_logger = logging.getLogger("nlq")
nlq_logger.setLevel(logging.INFO)

STATIC = db.ROOT / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if db.DB_PATH.exists():
        catalog.load()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


class AskBody(BaseModel):
    question: str
    database: str = "ecommerce"


class TryBody(BaseModel):
    question: str
    sql: str
    database: str = "ecommerce"


class LinkBody(BaseModel):
    primary_key: str
    foreign_key: str
    status: str


class FilterBody(BaseModel):
    col: str
    op: str
    value: str | int | float | None = None


class SortBody(BaseModel):
    col: str
    dir: str = "asc"


class ViewBody(BaseModel):
    columns: list[str] = []
    filters: list[FilterBody] = []
    sort: list[SortBody] = []
    page: int = 1
    page_size: int = db.ROW_CAP


class ModelBody(BaseModel):
    provider: str
    model: str | None = None


class HistorySettingsBody(BaseModel):
    history_retention_days: int


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/databases")
def databases() -> list[dict]:
    return db.list_databases()


@app.get("/usage")
def usage() -> dict:
    return history.usage()


@app.get("/models")
def models() -> list[dict]:
    return llm.list_providers()


@app.post("/settings/model")
def settings_model(body: ModelBody) -> dict:
    try:
        return llm.select_provider(body.provider, body.model)
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/settings/app")
def settings_app() -> dict:
    return app_settings.load()


@app.post("/settings/app")
def settings_app_update(body: HistorySettingsBody) -> dict:
    try:
        saved = app_settings.save({"history_retention_days": body.history_retention_days})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    removed = history.purge(saved["history_retention_days"])
    saved["purged"] = removed
    return saved


@app.get("/schema")
def schema(database: str = "ecommerce") -> list[dict]:
    info = _catalog(database)
    return [{"name": table.name, "description": table.description} for table in info.tables]


@app.get("/schema/{table}")
def schema_table(table: str, database: str = "ecommerce") -> dict:
    info = _catalog(database)
    found = info.table(table)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Unknown table: {table}")
    return {
        "name": found.name,
        "description": found.description,
        "columns": [
            {
                "name": column.name,
                "type": column.type,
                "key": column.key,
                "comment": column.comment,
            }
            for column in found.columns
        ],
    }


@app.post("/ask")
def ask(body: AskBody) -> dict:
    return generate.ask(body.question, body.database)


@app.post("/try")
def try_question(body: TryBody) -> dict:
    if body.database not in db.DATABASES:
        raise HTTPException(status_code=404, detail=f"Unknown database: {body.database}")
    return generate.try_sql(body.question, body.sql, body.database)


@app.get("/datasets/{dataset_id}/mapping")
def dataset_mapping(dataset_id: str) -> dict:
    if dataset_id not in db.DATABASES:
        raise HTTPException(status_code=404, detail=f"Unknown database: {dataset_id}")
    if not profile.path_for(dataset_id).exists():
        # Build a draft from the live DuckDB if none exists yet.
        try:
            profile.profile(dataset_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    return profile.mapping(dataset_id)


@app.post("/datasets/{dataset_id}/links")
def dataset_links(dataset_id: str, body: LinkBody) -> dict:
    if dataset_id not in db.DATABASES:
        raise HTTPException(status_code=404, detail=f"Unknown database: {dataset_id}")
    try:
        document = profile.update_link(
            dataset_id, body.primary_key, body.foreign_key, body.status
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    catalog.load(dataset_id, force=True)
    return {
        "id": dataset_id,
        "links": document.get("links") or [],
    }


@app.get("/history")
def history_list() -> list[dict]:
    return history.list_reports()


@app.get("/recommendations")
def recommendations(database: str = "ecommerce") -> list[dict]:
    if database not in db.DATABASES:
        raise HTTPException(status_code=404, detail=f"Unknown database: {database}")
    try:
        # File first; if missing, generate once via the LLM and save.
        return recommend.ensure(database)
    except Exception as exc:
        nlq_logger.warning("recommendations unavailable for %s: %s", database, exc)
        # Keep the UI usable when the LLM cannot invent starters yet.
        return recommend.load(database)


@app.get("/reports/{report_id}")
def report(report_id: int) -> dict:
    found = history.get_report(report_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Unknown report: {report_id}")
    if found.get("error"):
        nice = errors.friendly(found["error"])
        if nice:
            found["error_title"] = nice["title"]
            found["error"] = nice["detail"]
    return found


@app.post("/reports/{report_id}/view")
def report_view(report_id: int, body: ViewBody) -> dict:
    found = history.get_report(report_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"Unknown report: {report_id}")
    if not found.get("sql"):
        raise HTTPException(status_code=400, detail="This report has no SQL to re-fetch.")
    known = [name for name in found.get("columns") or [] if isinstance(name, str)]
    if not known:
        raise HTTPException(status_code=400, detail="This report has no fields to filter.")
    spec = body.model_dump()
    try:
        result = runner.view(found["sql"], known, spec, found.get("database") or "ecommerce")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except runner.QueryTimeout as exc:
        return _view_error(found, str(exc))
    except Exception as exc:
        return _view_error(found, str(exc))
    chart = charts.choose(result["columns"], result["rows"], found.get("chart"), found.get("question") or "")
    return {
        "id": found["id"],
        "question": found["question"],
        "title": found["title"],
        "sql": found["sql"],
        "assumptions": found["assumptions"],
        "reason": None,
        "answer_type": "sql",
        "chart": chart,
        "columns": result["columns"],
        "rows": result["rows"],
        "row_count": len(result["rows"]),
        "total": result["total"],
        "error": None,
    }


def _view_error(found: dict, message: str) -> dict:
    return {
        "id": found["id"],
        "question": found["question"],
        "title": found["title"],
        "sql": found["sql"],
        "assumptions": found["assumptions"],
        "reason": None,
        "answer_type": "sql",
        "chart": found.get("chart"),
        "columns": found.get("columns") or [],
        "rows": [],
        "row_count": 0,
        "total": 0,
        "error": message,
    }


def _catalog(database: str):
    if database not in db.DATABASES:
        raise HTTPException(status_code=404, detail=f"Unknown database: {database}")
    try:
        return catalog.load(database)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
