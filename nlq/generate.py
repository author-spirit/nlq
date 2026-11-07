"""Ask path: pick (optional) → generate → repair (on failure)."""

from __future__ import annotations

import json
import logging
import re
import time

from nlq import catalog, charts, db, errors, guard, history, prompts, runner
from nlq.guard import GuardError
from nlq.llm import LLMError, complete, last_usage, resolve
from nlq.runner import QueryTimeout

logger = logging.getLogger("nlq")

PICK_TOKEN_LIMIT = 6000
REPAIR_MAX = 2

PICK_PROMPT = """You choose which tables are needed to answer the question.
Return JSON only: {{"tables": ["table_a", "table_b"]}}
Use only names from this list. Prefer the smallest useful set.

Tables:
{tables}

Question:
{question}
"""


def try_sql(question: str, sql: str, database: str = "ecommerce") -> dict:
    """Run a trusted recommendation SQL without calling the LLM."""
    from nlq import recommend

    started = time.perf_counter()
    context = {
        "question": question,
        "database": database,
        "pick": "skipped",
        "repair": 0,
    }
    if database not in db.DATABASES:
        return _finish("error", context, started, error=f"Unknown database: {database}")
    try:
        question = guard.check_question(question)
        context["question"] = question
    except GuardError as exc:
        return _finish("error", context, started, error=str(exc))

    trusted = {item["sql"].strip() for item in recommend.load(database)}
    if sql.strip() not in trusted:
        return _finish(
            "error",
            context,
            started,
            error="SQL is not a stored recommendation for this database.",
        )

    try:
        sql = guard.check_sql(sql)
        _explain(sql, database)
        result = runner.run(sql, database=database)
    except (GuardError, QueryTimeout) as exc:
        return _finish(
            "ok",
            context,
            started,
            title=question,
            sql=sql,
            assumptions=[],
            reason=None,
            answer_type="sql",
            error=str(exc),
        )
    except Exception as exc:
        return _finish(
            "ok",
            context,
            started,
            title=question,
            sql=sql,
            assumptions=[],
            reason=None,
            answer_type="sql",
            error=str(exc),
        )
    chart = charts.choose(result["columns"], result["rows"], None, question)
    return _finish(
        "ok",
        context,
        started,
        title=question,
        sql=sql,
        assumptions=[],
        reason=None,
        answer_type="sql",
        chart=chart,
        columns=result["columns"],
        rows=result["rows"],
        row_count=len(result["rows"]),
    )


def ask(question: str, database: str = "ecommerce") -> dict:
    started = time.perf_counter()
    context = {
        "question": question,
        "database": database,
        "pick": "skipped",
        "repair": 0,
    }
    if database not in db.DATABASES:
        return _finish("error", context, started, error=f"Unknown database: {database}")
    try:
        question = guard.check_question(question)
        context["question"] = question
    except GuardError as exc:
        return _finish("error", context, started, error=str(exc))

    try:
        info = catalog.load(database)
    except FileNotFoundError as exc:
        return _finish("error", context, started, error=str(exc))

    schema_text = info.prompt_text
    picked_names: list[str] | None = None
    tokens = catalog.estimate_tokens(info.prompt_text)
    if tokens > PICK_TOKEN_LIMIT:
        try:
            picked_names = _pick(question, info)
            context["pick"] = "ok"
            schema_text = info.prompt_for(picked_names)
            logger.info(
                "pick=ok tables=%s tokens~%s→%s",
                picked_names,
                tokens,
                catalog.estimate_tokens(schema_text),
            )
        except (LLMError, ValueError, json.JSONDecodeError) as exc:
            context["pick"] = "failed"
            logger.warning("pick failed, using full schema: %s", exc)
            schema_text = info.prompt_text
    else:
        context["pick"] = "skipped"

    try:
        raw = complete(prompts.messages(question, schema_text, db.DIALECT, database=database))
        generated = _parse(raw)
    except (LLMError, ValueError, json.JSONDecodeError) as exc:
        return _finish("error", context, started, error=str(exc))

    title = generated["title"]
    assumptions = generated["assumptions"]
    reason = generated["reason"]
    if generated["answer_type"] == "schema":
        try:
            columns = info.schema_columns(generated["tables"] or None)
        except KeyError as exc:
            return _finish(
                "ok",
                context,
                started,
                title=title,
                assumptions=assumptions,
                reason=reason,
                answer_type="schema",
                error=f"Unknown table: {exc.args[0]}",
            )
        return _finish(
            "ok",
            context,
            started,
            title=title,
            assumptions=assumptions,
            reason=reason,
            answer_type="schema",
            columns=columns,
            row_count=len(columns),
            chart={"type": "table", "x": "", "y": [], "series": None},
        )

    sql = generated["sql"]
    if not sql:
        return _finish(
            "ok",
            context,
            started,
            title=title,
            assumptions=assumptions,
            reason=reason,
            answer_type="sql",
            sql=None,
        )

    last_error = None
    for attempt in range(REPAIR_MAX + 1):
        try:
            sql = guard.check_sql(sql)
            _explain(sql, database)
            result = runner.run(sql, database=database)
            chart = charts.choose(result["columns"], result["rows"], generated["chart"], question)
            return _finish(
                "ok",
                context,
                started,
                title=title,
                sql=sql,
                assumptions=assumptions,
                reason=reason,
                answer_type="sql",
                chart=chart,
                columns=result["columns"],
                rows=result["rows"],
                row_count=len(result["rows"]),
            )
        except (GuardError, QueryTimeout, Exception) as exc:
            last_error = str(exc)
            if attempt >= REPAIR_MAX:
                break
            context["repair"] = attempt + 1
            widen = _needs_wider_schema(last_error)
            if widen and picked_names is not None:
                schema_text = info.prompt_text
                picked_names = None
                logger.info("repair widening to full schema after: %s", last_error)
            try:
                raw, generated, sql, title, assumptions, reason = _repair(
                    question,
                    schema_text,
                    database,
                    raw,
                    last_error,
                )
            except (LLMError, ValueError, json.JSONDecodeError) as repair_exc:
                last_error = str(repair_exc)
                break

    return _finish(
        "ok",
        context,
        started,
        title=title,
        sql=sql,
        assumptions=assumptions,
        reason=reason,
        answer_type="sql",
        error=last_error,
    )


def _pick(question: str, info: catalog.Catalog) -> list[str]:
    lines = []
    for item in info.table_summaries():
        note = item["description"] or ""
        lines.append(f"- {item['name']}" + (f": {note}" if note else ""))
    raw = complete(
        [
            {
                "role": "system",
                "content": PICK_PROMPT.format(tables="\n".join(lines), question=question),
            },
            {"role": "user", "content": "Pick the tables."},
        ]
    )
    names = _parse_pick(raw)
    known = {table.name for table in info.tables}
    chosen = [name for name in names if name in known]
    if not chosen:
        raise ValueError("pick returned no known tables")
    return info.fk_neighbours(chosen)


def _parse_pick(raw: str) -> list[str]:
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    payload = json.loads(text)
    if isinstance(payload, list):
        return [str(item) for item in payload]
    if not isinstance(payload, dict):
        raise ValueError("pick JSON must be an object or list")
    tables = payload.get("tables") or []
    if isinstance(tables, str):
        tables = [tables]
    if not isinstance(tables, list):
        raise ValueError("pick tables must be a list")
    return [str(item) for item in tables]


def _repair(question, schema_text, database, previous_raw, error_text):
    messages = prompts.messages(question, schema_text, db.DIALECT, database=database)
    messages.append({"role": "assistant", "content": previous_raw})
    messages.append(
        {
            "role": "user",
            "content": (
                "The database rejected that SQL.\n"
                f"Error: {error_text}\n"
                "Return corrected JSON only with a fixed SELECT (or sql null)."
            ),
        }
    )
    raw = complete(messages)
    generated = _parse(raw)
    sql = generated["sql"]
    if not sql:
        raise ValueError(generated.get("reason") or "repair returned no SQL")
    return (
        raw,
        generated,
        sql,
        generated["title"],
        generated["assumptions"],
        generated["reason"],
    )


def _needs_wider_schema(message: str) -> bool:
    lower = (message or "").lower()
    return any(
        token in lower
        for token in (
            "table with name",
            "does not exist",
            "not found",
            "unknown table",
            "catalog error",
            "binder error",
        )
    )


def _explain(sql: str, database: str) -> None:
    con = db.connect(database)
    try:
        db.explain(con, sql)
    finally:
        con.close()


def _parse(raw: str) -> dict:
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Model JSON must be an object.")
    sql = payload.get("sql")
    if isinstance(sql, str):
        sql = sql.strip() or None
    else:
        sql = None
    tables = payload.get("tables") or []
    if isinstance(tables, str):
        tables = [tables]
    if not isinstance(tables, list):
        raise ValueError("tables must be a list.")
    answer_type = payload.get("answer_type")
    if answer_type not in {"sql", "schema"}:
        answer_type = "schema" if sql is None and tables else "sql"
    assumptions = payload.get("assumptions") or []
    if not isinstance(assumptions, list):
        assumptions = [str(assumptions)]
    title = payload.get("title") or ""
    reason = payload.get("reason")
    return {
        "answer_type": answer_type,
        "sql": sql,
        "tables": [str(item) for item in tables],
        "title": str(title),
        "chart": _chart(payload.get("chart")),
        "assumptions": [str(item) for item in assumptions],
        "reason": None if reason is None else str(reason),
    }


def _chart(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    y = value.get("y") or []
    if isinstance(y, str):
        y = [y]
    if not isinstance(y, list):
        y = []
    series = value.get("series")
    chart_type = value.get("type")
    return {
        "type": chart_type if chart_type in {"bar", "line", "pie", "scatter", "table"} else "table",
        "x": "" if value.get("x") is None else str(value.get("x")),
        "y": [str(item) for item in y if item],
        "series": None if not series else str(series),
    }


def _finish(generate_status: str, context: dict, started: float, **fields) -> dict:
    pick = context.get("pick") or "skipped"
    repair = int(context.get("repair") or 0)
    logger.info("pick=%s, generate=%s, repair=%s", pick, generate_status, repair)
    result = {
        "title": "",
        "sql": None,
        "assumptions": [],
        "reason": None,
        "answer_type": None,
        "chart": None,
        "columns": [],
        "rows": [],
        "row_count": 0,
        "error": None,
    }
    result.update(fields)
    result["pick"] = pick
    result["generate"] = generate_status
    result["repair"] = repair
    if result.get("error"):
        logger.error("generate failed: %s", result["error"])
    result["id"] = _save(generate_status, context, started, result)
    if result.get("error"):
        nice = errors.friendly(result["error"])
        if nice:
            result["error_title"] = nice["title"]
            result["error"] = nice["detail"]
    return result


def _save(generate_status: str, context: dict, started: float, result: dict) -> int | None:
    try:
        model = resolve()[2]
    except LLMError:
        model = ""
    try:
        return history.save(
            {
                "question": context.get("question"),
                "database": context.get("database"),
                "model": model,
                "title": result.get("title"),
                "sql": result.get("sql"),
                "chart": result.get("chart"),
                "assumptions": result.get("assumptions"),
                "status": "error" if result.get("error") or generate_status == "error" else "ok",
                "error": result.get("error"),
                "retries": int(context.get("repair") or 0),
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "tokens_in": last_usage.get("prompt_tokens"),
                "tokens_out": last_usage.get("completion_tokens"),
                "row_count": result.get("row_count") or 0,
                "rows": result.get("rows") or [],
                "columns": result.get("columns") or [],
                "answer_type": result.get("answer_type"),
                "pick": context.get("pick") or "skipped",
                "generate": generate_status,
                "repair": int(context.get("repair") or 0),
            }
        )
    except Exception:
        logger.exception("history save failed")
        return None
