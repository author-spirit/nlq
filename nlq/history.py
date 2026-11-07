"""Report history in a sqlite file separate from the analytics database."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from nlq import app_settings, db

PATH = db.ROOT / "data" / "sqlite" / "history.sqlite"
PROMPT_VERSION = "v1"
SNAPSHOT_LIMIT = 200
logger = logging.getLogger("nlq.history")


def save(report: dict) -> int:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(PATH) as con:
        _ensure(con)
        _purge(con, app_settings.history_retention_days())
        rows = report.get("rows") or []
        snapshot = rows[:SNAPSHOT_LIMIT]
        cursor = con.execute(
            """
            INSERT INTO reports (
                created_at, question, model, prompt_version, sql, chart_spec,
                assumptions, status, error, retries, latency_ms, tokens_in,
                tokens_out, row_count, snapshot_rows, title, columns_json,
                answer_type, pick, generate, repair, database
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                report.get("question") or "",
                report.get("model") or "",
                PROMPT_VERSION,
                report.get("sql"),
                json.dumps(report.get("chart")),
                json.dumps(report.get("assumptions") or []),
                report.get("status") or "ok",
                report.get("error"),
                report.get("retries") or 0,
                report.get("latency_ms"),
                report.get("tokens_in"),
                report.get("tokens_out"),
                report.get("row_count") or 0,
                json.dumps(snapshot),
                report.get("title") or "",
                json.dumps(report.get("columns") or []),
                report.get("answer_type"),
                report.get("pick") or "skipped",
                report.get("generate") or "ok",
                report.get("repair") if report.get("repair") is not None else 0,
                report.get("database") or "ecommerce",
            ),
        )
        return int(cursor.lastrowid)


def purge(days: int | None = None) -> int:
    """Delete reports older than retention. Returns rows removed."""
    keep_days = days if days is not None else app_settings.history_retention_days()
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(PATH) as con:
        _ensure(con)
        return _purge(con, keep_days)


def _purge(con: sqlite3.Connection, days: int) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat(
        timespec="seconds"
    )
    cursor = con.execute("DELETE FROM reports WHERE created_at < ?", (cutoff,))
    removed = int(cursor.rowcount or 0)
    if removed:
        logger.info("history purged %s rows older than %s days", removed, days)
    return removed


def list_reports(limit: int = 50) -> list[dict]:
    if not PATH.exists():
        return []
    with sqlite3.connect(PATH) as con:
        _ensure(con)
        _purge(con, app_settings.history_retention_days())
        found = con.execute(
            """
            SELECT id, created_at, question, title, status
            FROM reports
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "id": row[0],
            "created_at": row[1],
            "question": row[2],
            "title": row[3],
            "status": row[4],
        }
        for row in found
    ]


def usage() -> dict:
    tokens_in = 0
    tokens_out = 0
    asks = 0
    failures = 0
    chart_failures = 0
    chart_ok = 0
    latest_model = ""
    by_day: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    if PATH.exists():
        with sqlite3.connect(PATH) as con:
            _ensure(con)
            rows = con.execute(
                """
                SELECT created_at, model, status, error, question, chart_spec,
                       tokens_in, tokens_out
                FROM reports
                ORDER BY id ASC
                """
            ).fetchall()
        for created_at, model, status, error, question, chart_spec, tin, tout in rows:
            asks += 1
            if model:
                latest_model = model
            tin_n = int(tin or 0)
            tout_n = int(tout or 0)
            tokens_in += tin_n
            tokens_out += tout_n
            failed = status == "error" or bool(error)
            if failed:
                failures += 1
            chart_bad = _chart_failed(question or "", chart_spec, status or "", error)
            if chart_bad:
                chart_failures += 1
            elif not failed:
                chart = None
                try:
                    chart = json.loads(chart_spec) if chart_spec else None
                except json.JSONDecodeError:
                    chart = None
                if chart and chart.get("type") not in {None, "table"}:
                    chart_ok += 1
            day = (created_at or "")[:10] or "unknown"
            bucket = by_day.setdefault(
                day, {"day": day, "ok": 0, "error": 0, "tokens_in": 0, "tokens_out": 0}
            )
            if failed:
                bucket["error"] += 1
            else:
                bucket["ok"] += 1
            bucket["tokens_in"] += tin_n
            bucket["tokens_out"] += tout_n
            model_name = model or "unknown"
            model_bucket = by_model.setdefault(
                model_name,
                {
                    "model": model_name,
                    "asks": 0,
                    "ok": 0,
                    "error": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                },
            )
            model_bucket["asks"] += 1
            if failed:
                model_bucket["error"] += 1
            else:
                model_bucket["ok"] += 1
            model_bucket["tokens_in"] += tin_n
            model_bucket["tokens_out"] += tout_n
    provider = ""
    model = latest_model
    try:
        from nlq.llm import resolve

        provider, _, model, _ = resolve()
    except Exception:
        pass
    days = sorted(by_day.values(), key=lambda item: item["day"])
    models = sorted(by_model.values(), key=lambda item: (-item["asks"], item["model"]))
    return {
        "provider": provider,
        "model": model,
        "asks": asks,
        "failures": failures,
        "successes": max(0, asks - failures),
        "chart_failures": chart_failures,
        "chart_ok": chart_ok,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_total": tokens_in + tokens_out,
        "asks_by_day": [{"day": d["day"], "ok": d["ok"], "error": d["error"]} for d in days],
        "tokens_by_day": [
            {"day": d["day"], "tokens_in": d["tokens_in"], "tokens_out": d["tokens_out"]}
            for d in days
        ],
        "by_model": models,
        "outcomes": {"ok": max(0, asks - failures), "error": failures},
        "charts": {"ok": chart_ok, "failed": chart_failures},
        "stats": [
            {"n": 1, "label": "Tokens in", "value": tokens_in},
            {"n": 2, "label": "Tokens out", "value": tokens_out},
            {"n": 3, "label": "Tokens total", "value": tokens_in + tokens_out},
            {"n": 4, "label": "Asks", "value": asks},
            {"n": 5, "label": "Successes", "value": max(0, asks - failures)},
            {"n": 6, "label": "Failures", "value": failures},
            {"n": 7, "label": "Charts ok", "value": chart_ok},
            {"n": 8, "label": "Chart failures", "value": chart_failures},
        ],
    }


def _chart_failed(question: str, chart_spec: str | None, status: str, error: str | None) -> bool:
    lower = question.lower()
    wants = any(word in lower for word in ("chart", "bar", "bars", "pie", "line", "scatter"))
    if not wants:
        return False
    if status == "error" or error:
        return True
    try:
        chart = json.loads(chart_spec) if chart_spec else None
    except json.JSONDecodeError:
        return True
    if not chart or chart.get("type") in {None, "table"}:
        return True
    return False


def get_report(report_id: int) -> dict | None:
    if not PATH.exists():
        return None
    with sqlite3.connect(PATH) as con:
        _ensure(con)
        row = con.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if row is None:
            return None
        names = [item[1] for item in con.execute("PRAGMA table_info(reports)").fetchall()]
    record = dict(zip(names, row))
    return {
        "id": record["id"],
        "created_at": record["created_at"],
        "question": record["question"],
        "title": record["title"],
        "sql": record["sql"],
        "assumptions": json.loads(record["assumptions"] or "[]"),
        "reason": None,
        "answer_type": record["answer_type"],
        "chart": json.loads(record["chart_spec"]) if record["chart_spec"] else None,
        "columns": json.loads(record["columns_json"] or "[]"),
        "rows": json.loads(record["snapshot_rows"] or "[]"),
        "row_count": record["row_count"],
        "error": record["error"],
        "database": record.get("database") or "ecommerce",
        "pick": record.get("pick") or "skipped",
        "generate": record.get("generate") or "ok",
        "repair": int(record.get("repair") or record.get("retries") or 0),
    }


def _ensure(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            question TEXT NOT NULL,
            model TEXT,
            prompt_version TEXT,
            sql TEXT,
            chart_spec TEXT,
            assumptions TEXT,
            status TEXT,
            error TEXT,
            retries INTEGER,
            latency_ms INTEGER,
            tokens_in INTEGER,
            tokens_out INTEGER,
            row_count INTEGER,
            snapshot_rows TEXT,
            title TEXT,
            columns_json TEXT,
            answer_type TEXT,
            pick TEXT,
            generate TEXT,
            repair INTEGER,
            database TEXT
        )
        """
    )
