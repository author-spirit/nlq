"""DuckDB adapter. The rest of the engine talks only to these functions."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "duckdb" / "ecommerce.duckdb"
DEMO_SCALE_PATH = ROOT / "data" / "duckdb" / "demo_scale.duckdb"
DIALECT = "duckdb"
ROW_CAP = 1000
QUERY_TIMEOUT_S = 15
DATASETS_PATH = ROOT / "data" / "datasets.json"
HINTS_DIR = ROOT / "hints"
HINTS_PATH = ROOT / "hints.json"  # legacy shim; prefer HINTS_DIR

_BUILTIN = {
    "ecommerce": DB_PATH,
    "demo_scale": DEMO_SCALE_PATH,
}
DATABASES: dict[str, Path] = dict(_BUILTIN)


def reload_databases() -> dict[str, Path]:
    """Rebuild DATABASES from builtins + data/datasets.json."""
    found = dict(_BUILTIN)
    if DATASETS_PATH.exists():
        try:
            document = json.loads(DATASETS_PATH.read_text())
        except json.JSONDecodeError:
            document = {}
        if isinstance(document, dict):
            for name, raw in document.items():
                if not isinstance(name, str) or not isinstance(raw, str):
                    continue
                path = Path(raw)
                if not path.is_absolute():
                    path = ROOT / path
                found[name] = path
    DATABASES.clear()
    DATABASES.update(found)
    return DATABASES


reload_databases()


def connect(database: str = "ecommerce"):
    path = DATABASES.get(database)
    if path is None:
        raise KeyError(database)
    if not path.exists():
        raise FileNotFoundError(
            f"Database file is missing: {path}. Run python -m nlq.build_db"
        )
    con = duckdb.connect(str(path), read_only=True)
    lock(con)
    return con


def list_databases() -> list[dict]:
    """List datasets. Prefer table counts from hints (no DuckDB open per call)."""
    labels = _labels()
    hint_counts = _hint_table_counts()
    found = []
    for name, path in DATABASES.items():
        if not path.exists():
            continue
        try:
            shown = str(path.relative_to(ROOT))
        except ValueError:
            shown = str(path)
        tables = hint_counts.get(name)
        if tables is None:
            tables = _count_tables(name)
        found.append(
            {
                "id": name,
                "label": labels.get(name) or name.replace("_", " ").title(),
                "path": shown,
                "tables": tables,
            }
        )
    return found


def _hint_table_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    if not HINTS_DIR.is_dir():
        return counts
    for path in HINTS_DIR.glob("*.json"):
        try:
            document = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if not isinstance(document, dict):
            continue
        tables = document.get("tables")
        if isinstance(tables, dict) and tables:
            counts[path.stem] = len(tables)
    return counts


def _count_tables(name: str) -> int:
    try:
        con = connect(name)
        try:
            return int(
                con.execute(
                    """
                    SELECT count(*) FROM information_schema.tables
                    WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
                    """
                ).fetchone()[0]
            )
        finally:
            con.close()
    except Exception:
        return 0


def _labels() -> dict[str, str]:
    labels: dict[str, str] = {}
    if HINTS_DIR.is_dir():
        for path in HINTS_DIR.glob("*.json"):
            try:
                document = json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
            if isinstance(document, dict) and document.get("label"):
                labels[path.stem] = str(document["label"])
    # Legacy monolith fallback
    if HINTS_PATH.exists():
        try:
            document = json.loads(HINTS_PATH.read_text())
        except json.JSONDecodeError:
            document = {}
        if isinstance(document, dict):
            for name, info in document.items():
                if name in labels:
                    continue
                if isinstance(info, dict) and info.get("label"):
                    labels[name] = str(info["label"])
    return labels


def lock(con) -> None:
    con.execute("SET enable_external_access=false")
    con.execute("SET memory_limit='1GB'")
    con.execute("SET lock_configuration=true")


def explain(con, sql: str) -> None:
    con.execute("EXPLAIN " + sql).fetchall()


def run(con, sql: str, params: list | None = None):
    cursor = con.execute(sql, params or [])
    return cursor.description, cursor.fetchall()


def interrupt(con) -> None:
    con.interrupt()


def fetch_columns(con) -> list[tuple]:
    return con.execute(
        """
        SELECT table_name, column_name, data_type, is_nullable, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = 'main'
        ORDER BY table_name, ordinal_position
        """
    ).fetchall()


def fetch_constraints(con) -> list[tuple]:
    return con.execute(
        """
        SELECT table_name, constraint_type, constraint_column_names,
               referenced_table, referenced_column_names
        FROM duckdb_constraints()
        WHERE schema_name = 'main'
          AND constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
        """
    ).fetchall()
