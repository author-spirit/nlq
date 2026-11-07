"""Import a SQL dump or CSV directory into data/duckdb/<id>.duckdb."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import duckdb

from nlq import db, profile

DATASETS_PATH = db.ROOT / "data" / "datasets.json"
DUCK_DIR = db.ROOT / "data" / "duckdb"

SKIP_PREFIXES = (
    "SET ",
    "USE ",
    "LOCK ",
    "UNLOCK ",
    "START TRANSACTION",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
    "DELIMITER",
    "/*!",
)


def import_sql(database_id: str, sql_path: Path, *, label: str | None = None) -> Path:
    text = sql_path.read_text()
    kind = _source_kind(sql_path, text)
    statements = _normalize_statements(text)
    path = _prepare_db_path(database_id)
    con = duckdb.connect(str(path))
    try:
        for statement in statements:
            try:
                con.execute(statement)
            except Exception as exc:
                # Skip statements DuckDB still rejects after normalization.
                if _is_skippable(statement, exc):
                    continue
                raise RuntimeError(f"Failed on statement:\n{statement[:400]}\n{exc}") from exc
    finally:
        con.close()
    _register(database_id, path)
    profile.profile(
        database_id,
        path=path,
        source={"kind": kind, "file": _rel(sql_path)},
        label=label,
    )
    return path


def import_csv_dir(database_id: str, csv_dir: Path, *, label: str | None = None) -> Path:
    csv_dir = csv_dir.resolve()
    if not csv_dir.is_dir():
        raise FileNotFoundError(csv_dir)
    files = sorted(csv_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files in {csv_dir}")
    path = _prepare_db_path(database_id)
    con = duckdb.connect(str(path))
    try:
        for file in files:
            name = _safe_table_name(file.stem)
            csv_path = str(file).replace("'", "''")
            con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM read_csv_auto(\'{csv_path}\', header=true)')
    finally:
        con.close()
    _register(database_id, path)
    profile.profile(
        database_id,
        path=path,
        source={"kind": "csv_dir", "file": _rel(csv_dir)},
        label=label,
    )
    return path


def _prepare_db_path(database_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", database_id):
        raise ValueError("database id must be alphanumeric/underscore and start with a letter")
    DUCK_DIR.mkdir(parents=True, exist_ok=True)
    path = DUCK_DIR / f"{database_id}.duckdb"
    for extra in (path, Path(str(path) + ".wal")):
        if extra.exists():
            extra.unlink()
    return path


def _register(database_id: str, path: Path) -> None:
    registry = {}
    if DATASETS_PATH.exists():
        try:
            registry = json.loads(DATASETS_PATH.read_text()) or {}
        except json.JSONDecodeError:
            registry = {}
    if not isinstance(registry, dict):
        registry = {}
    try:
        shown = str(path.relative_to(db.ROOT))
    except ValueError:
        shown = str(path)
    registry[database_id] = shown
    DATASETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATASETS_PATH.write_text(json.dumps(registry, indent=2) + "\n")
    db.reload_databases()


def _source_kind(path: Path, text: str) -> str:
    lower = text.lower()
    name = path.name.lower()
    if "mysql" in name or "engine=innodb" in lower or "`" in text:
        return "mysql_dump"
    if "postgres" in name or "double precision" in lower:
        return "postgres_dump"
    return "sql_dump"


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(db.ROOT))
    except ValueError:
        return str(path)


def _safe_table_name(stem: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", stem)
    if not name or name[0].isdigit():
        name = "t_" + name
    return name


def _normalize_statements(text: str) -> list[str]:
    cleaned = _strip_comments(text)
    cleaned = cleaned.replace("\r\n", "\n")
    # MySQL backticks → quotes
    cleaned = cleaned.replace("`", '"')
    # Common type / dialect rewrites
    replacements = [
        (r"\bDOUBLE PRECISION\b", "DOUBLE"),
        (r"\bDATETIME\b", "TIMESTAMP"),
        (r"\bTINYINT\b", "INTEGER"),
        (r"\bSMALLINT\b", "INTEGER"),
        (r"\bMEDIUMINT\b", "INTEGER"),
        (r"\bBIGINT\b", "BIGINT"),
        (r"\bINT\b", "INTEGER"),
        (r"\bSERIAL\b", "INTEGER"),
        (r"\bBIGSERIAL\b", "BIGINT"),
        (r"\bBOOLEAN\b", "BOOLEAN"),
        (r"\bBOOL\b", "BOOLEAN"),
        (r"ENGINE\s*=\s*\w+", ""),
        (r"DEFAULT CHARSET\s*=\s*\w+", ""),
        (r"CHARSET\s*=\s*\w+", ""),
        (r"COLLATE\s*=\s*\w+", ""),
        (r"CHARACTER SET\s+\w+", ""),
        (r"COLLATE\s+\w+", ""),
        (r"AUTO_INCREMENT", ""),
        (r"UNSIGNED", ""),
        (r"CONSTRAINT\s+\"[^\"]+\"\s+", ""),
        (r"CONSTRAINT\s+\w+\s+", ""),
    ]
    for pattern, repl in replacements:
        cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)

    statements = []
    for raw in _split_sql(cleaned):
        statement = raw.strip().rstrip(";").strip()
        if not statement:
            continue
        upper = statement.lstrip().upper()
        if any(upper.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue
        if upper.startswith("CREATE INDEX") or upper.startswith("CREATE UNIQUE INDEX"):
            continue
        if upper.startswith("ALTER TABLE") and "OWNER TO" in upper:
            continue
        statements.append(statement)
    return statements


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("--"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _split_sql(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
        elif ch == ";" and not in_single and not in_double:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf))
    return parts


def _is_skippable(statement: str, exc: Exception) -> bool:
    message = str(exc).lower()
    upper = statement.lstrip().upper()
    if upper.startswith("ALTER TABLE"):
        return True
    if "not implemented" in message or "parser error" in message:
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Import SQL dump or CSV dir into DuckDB + hints")
    parser.add_argument("--id", required=True, help="Dataset id")
    parser.add_argument("--sql", type=Path, help="Path to Postgres/MySQL SQL dump")
    parser.add_argument("--csv-dir", type=Path, help="Directory of CSV files")
    parser.add_argument("--label", help="Display label for hints")
    args = parser.parse_args()
    if bool(args.sql) == bool(args.csv_dir):
        parser.error("Provide exactly one of --sql or --csv-dir")
    if args.sql:
        path = import_sql(args.id, args.sql, label=args.label)
    else:
        path = import_csv_dir(args.id, args.csv_dir, label=args.label)
    print(path)
    print(profile.path_for(args.id))


if __name__ == "__main__":
    main()
