"""Suggested questions for a dataset. Curated files live under recommendations/."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from nlq import catalog, db, guard, llm, runner
from nlq.guard import GuardError

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "recommendations"
logger = logging.getLogger("nlq")

GENERATE_PROMPT = """You invent starter analytics questions for this {dialect} database.

Schema:
{schema}

Return JSON only: a list of 5 objects.
Each object: {{"question": short natural-language question, "sql": one SELECT that answers it}}
Rules:
- Use only tables and columns in the schema.
- Prefer GROUP BY and ORDER BY charts over raw dumps.
- One SELECT (or WITH ... SELECT) per item. No writes.
- Keep questions short and useful for a first-time user.
"""


def path_for(database: str) -> Path:
    return DIR / f"{database}.json"


def load(database: str = "ecommerce") -> list[dict]:
    path = path_for(database)
    if not path.exists():
        return []
    document = json.loads(path.read_text())
    if not isinstance(document, list):
        raise ValueError(f"{path.name} must be a list.")
    return [_clean(item) for item in document if isinstance(item, dict)]


def save(database: str, items: list[dict]) -> Path:
    DIR.mkdir(parents=True, exist_ok=True)
    path = path_for(database)
    path.write_text(json.dumps(items, indent=2) + "\n")
    return path


def ensure(database: str = "ecommerce") -> list[dict]:
    """Return recommendations, generating them the first time a dataset has none."""
    existing = load(database)
    if existing:
        return existing
    return generate(database)


def on_dataset_loaded(database: str) -> list[dict]:
    """Call after a new analytics DB is built or registered under data/."""
    return ensure(database)


def generate(database: str = "ecommerce") -> list[dict]:
    info = catalog.load(database)
    raw = llm.complete(
        [
            {
                "role": "system",
                "content": GENERATE_PROMPT.format(dialect=db.DIALECT, schema=info.prompt_text),
            },
            {"role": "user", "content": "Invent 5 starter questions with SQL."},
        ]
    )
    items = _parse(raw)
    kept = []
    for item in items:
        try:
            sql = guard.check_sql(item["sql"])
            con = db.connect(database)
            try:
                db.explain(con, sql)
            finally:
                con.close()
            runner.run(sql, database=database)
        except (GuardError, Exception) as exc:
            logger.warning("skip recommendation %r: %s", item.get("question"), exc)
            continue
        kept.append({"question": item["question"], "sql": sql})
        if len(kept) >= 5:
            break
    if not kept:
        raise ValueError("Could not generate any valid recommendations.")
    save(database, kept)
    return kept


def _clean(item: dict) -> dict:
    question = str(item.get("question") or "").strip()
    sql = str(item.get("sql") or "").strip()
    if not question or not sql:
        raise ValueError("Each recommendation needs question and sql.")
    return {"question": question, "sql": sql}


def _parse(raw: str) -> list[dict]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    document = json.loads(text)
    if not isinstance(document, list):
        raise ValueError("Recommendations must be a JSON list.")
    return [_clean(item) for item in document if isinstance(item, dict)]
