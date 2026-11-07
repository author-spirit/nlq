"""Run a guarded SELECT with a timeout and a row cap."""

from __future__ import annotations

import math
import re
import threading
from datetime import date, datetime
from decimal import Decimal

from nlq import db

QUERY_TIMEOUT_S = db.QUERY_TIMEOUT_S


class QueryTimeout(Exception):
    pass


OPS = {
    "=": "=",
    "!=": "!=",
    "<": "<",
    ">": ">",
    "<=": "<=",
    ">=": ">=",
    "like": "LIKE",
}

_INT = re.compile(r"^(?:TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT|UTINYINT|USMALLINT|UINTEGER|UBIGINT)$")
_FLOAT = re.compile(r"^(?:FLOAT|DOUBLE|REAL|DECIMAL|NUMERIC)(?:\(.*\))?$")


def wrap(sql: str, limit: int = db.ROW_CAP) -> str:
    return f"SELECT * FROM ( {sql} ) AS _nlq LIMIT {int(limit)}"


def quote_ident(name: str, known: list[str]) -> str:
    if name not in known:
        raise ValueError(f"Unknown column: {name}")
    return '"' + name.replace('"', '""') + '"'


def column_types(sql: str, database: str = "ecommerce") -> dict[str, str]:
    con = db.connect(database)
    try:
        rows = con.execute(f"DESCRIBE SELECT * FROM ( {sql} ) AS _nlq_types").fetchall()
    finally:
        con.close()
    return {str(row[0]): str(row[1]).upper() for row in rows}


def coerce_value(value, col_type: str | None, op: str):
    """Bind numbers as numbers so DOUBLE/INTEGER filters do not compare to VARCHAR."""
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value).strip()
    if op == "like":
        return text
    kind = (col_type or "").upper().split("(")[0]
    if kind == "BOOLEAN":
        return text.lower() in {"1", "true", "t", "yes"}
    if _INT.match(kind):
        try:
            return int(text)
        except ValueError:
            return int(float(text))
    if _FLOAT.match(kind) or kind.startswith("DECIMAL") or kind.startswith("NUMERIC"):
        return float(text)
    if text and re.fullmatch(r"-?\d+", text) and op in {"=", "!=", "<", ">", "<=", ">="}:
        return int(text)
    if text and re.fullmatch(r"-?\d+\.\d+", text) and op in {"=", "!=", "<", ">", "<=", ">="}:
        return float(text)
    return value


def compile_view(
    sql: str,
    known: list[str],
    spec: dict,
    types: dict[str, str] | None = None,
) -> tuple[str, list, str]:
    """Return data SQL, bound values, and a count SQL for the same filter."""
    selected = list(spec.get("columns") or known)
    if not selected:
        raise ValueError("Choose at least one field.")
    types = types or {}
    select_list = ", ".join(quote_ident(name, known) for name in selected)
    where = []
    params: list = []
    for item in spec.get("filters") or []:
        column = item.get("col")
        op = str(item.get("op") or "").lower()
        if op not in OPS:
            raise ValueError(f"Unknown operator: {op}")
        where.append(f"{quote_ident(column, known)} {OPS[op]} ?")
        try:
            params.append(coerce_value(item.get("value"), types.get(column), op))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid value for {column}: {item.get('value')}") from exc
    order = []
    for item in spec.get("sort") or []:
        column = item.get("col")
        direction = str(item.get("dir") or "asc").lower()
        if direction not in {"asc", "desc"}:
            raise ValueError(f"Unknown sort direction: {direction}")
        order.append(f"{quote_ident(column, known)} {direction.upper()}")
    page = max(1, int(spec.get("page") or 1))
    page_size = min(db.ROW_CAP, max(1, int(spec.get("page_size") or db.ROW_CAP)))
    offset = (page - 1) * page_size
    base = f"SELECT {select_list} FROM ( {sql} ) AS t"
    if where:
        base += " WHERE " + " AND ".join(where)
    count_sql = f"SELECT count(*) AS n FROM ( {base} ) AS c"
    data_sql = base
    if order:
        data_sql += " ORDER BY " + ", ".join(order)
    data_sql += f" LIMIT {page_size} OFFSET {offset}"
    return data_sql, params, count_sql


def view(sql: str, known: list[str], spec: dict, database: str = "ecommerce") -> dict:
    types = column_types(sql, database)
    data_sql, params, count_sql = compile_view(sql, known, spec, types)
    counted = execute(count_sql, database=database, params=params)
    total = counted["rows"][0][0] if counted["rows"] else 0
    result = execute(data_sql, database=database, params=params)
    result["total"] = total
    return result


def run(
    sql: str,
    database: str = "ecommerce",
    timeout: float = QUERY_TIMEOUT_S,
    params: list | None = None,
) -> dict:
    return execute(wrap(sql), database=database, timeout=timeout, params=params)


def execute(
    sql: str,
    database: str = "ecommerce",
    timeout: float = QUERY_TIMEOUT_S,
    params: list | None = None,
) -> dict:
    state: dict = {}

    def work() -> None:
        con = db.connect(database)
        state["con"] = con
        try:
            description, rows = db.run(con, sql, params)
            columns = [col[0] for col in description]
            state["value"] = {
                "columns": columns,
                "rows": [[json_safe(value) for value in row] for row in rows],
            }
        except BaseException as exc:
            state["error"] = exc
        finally:
            con.close()

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(timeout)
    timed_out = thread.is_alive()
    if timed_out:
        con = state.get("con")
        if con is not None:
            db.interrupt(con)
        thread.join()
    if "error" in state:
        if timed_out or _interrupted(state["error"]):
            raise QueryTimeout(f"Query exceeded {timeout} seconds.")
        raise state["error"]
    if timed_out or "value" not in state:
        raise QueryTimeout(f"Query exceeded {timeout} seconds.")
    return state["value"]


def json_safe(value):
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _interrupted(exc: BaseException) -> bool:
    return "interrupt" in str(exc).lower()
