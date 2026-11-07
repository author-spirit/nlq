"""Offline table profiling and FK link guessing for hints/<id>.json drafts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from nlq import db

HINTS_DIR = db.ROOT / "hints"
LOW_CARDINALITY_MAX = 50
SAMPLE_LIMIT = 10
OVERLAP_SAMPLE = 500
HIGH_OVERLAP = 0.98
MEDIUM_OVERLAP = 0.7
TEXT_TYPES = {"VARCHAR", "TEXT", "CHAR", "STRING"}
DATE_TYPES = {"DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP_NS", "DATETIME"}
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def path_for(database: str) -> Path:
    return HINTS_DIR / f"{database}.json"


def load_hints(database: str) -> dict:
    path = path_for(database)
    if not path.exists():
        return {}
    document = json.loads(path.read_text())
    if not isinstance(document, dict):
        return {}
    return document


def save_hints(database: str, document: dict) -> Path:
    HINTS_DIR.mkdir(parents=True, exist_ok=True)
    path = path_for(database)
    path.write_text(json.dumps(document, indent=2) + "\n")
    return path


def profile(
    database: str,
    *,
    path: Path | None = None,
    source: dict | None = None,
    label: str | None = None,
) -> dict:
    """Profile a DuckDB file and merge auto fields into hints/<id>.json."""
    existing = load_hints(database)
    db_path = path or db.DATABASES.get(database)
    if db_path is None:
        raise KeyError(database)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables_meta = _profile_tables(con)
        declared = _declared_links(con)
        guessed = _guess_links(con, tables_meta, declared)
    finally:
        con.close()

    merged_tables = _merge_tables(existing.get("tables") or {}, tables_meta)
    merged_links = _merge_links(existing.get("links") or [], declared, guessed)

    document = {
        "label": label or existing.get("label") or database.replace("_", " ").title(),
        "description": existing.get("description") or "",
        "tables": merged_tables,
        "links": merged_links,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if source is not None:
        document["source"] = source
    elif existing.get("source"):
        document["source"] = existing["source"]
    for key in ("src",):
        if key in existing and key not in document:
            document[key] = existing[key]
    save_hints(database, document)
    return document


def update_link(database: str, primary_key: str, foreign_key: str, status: str) -> dict:
    if status not in {"confirmed", "rejected"}:
        raise ValueError("status must be confirmed or rejected")
    document = load_hints(database)
    links = list(document.get("links") or [])
    found = False
    for link in links:
        if link.get("primary_key") == primary_key and link.get("foreign_key") == foreign_key:
            link["status"] = status
            link["needs_review"] = False
            # Keep profiler reason for audit, mark decision as user review.
            prior = link.get("reason") or ""
            if prior and prior != "user" and not prior.startswith("user:"):
                link["reason"] = f"user:{prior}"
            else:
                link["reason"] = link.get("reason") or "user"
            found = True
            break
    if not found:
        links.append(
            {
                "primary_key": primary_key,
                "foreign_key": foreign_key,
                "status": status,
                "confidence": 1.0 if status == "confirmed" else 0.0,
                "reason": "user",
                "needs_review": False,
            }
        )
    document["links"] = links
    save_hints(database, document)
    return document


def mapping(database: str) -> dict:
    document = load_hints(database)
    tables = []
    for name, meta in sorted((document.get("tables") or {}).items()):
        tables.append(
            {
                "name": name,
                "description": meta.get("description") or "",
                "row_count": meta.get("row_count"),
                "columns": list((meta.get("columns") or {}).keys()),
            }
        )
    return {
        "id": database,
        "label": document.get("label") or database,
        "description": document.get("description") or "",
        "generated_at": document.get("generated_at"),
        "source": document.get("source"),
        "tables": tables,
        "links": list(document.get("links") or []),
    }


def _profile_tables(con) -> dict[str, dict]:
    rows = con.execute(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'main'
        ORDER BY table_name, ordinal_position
        """
    ).fetchall()
    grouped: dict[str, dict] = {}
    for table_name, column_name, data_type in rows:
        table = grouped.setdefault(
            table_name,
            {"description": "", "row_count": 0, "columns": {}, "_types": {}},
        )
        table["columns"][column_name] = {"note": "", "samples": []}
        table["_types"][column_name] = data_type

    for table_name, table in grouped.items():
        ident = _ident(table_name)
        table["row_count"] = int(con.execute(f"SELECT count(*) FROM {ident}").fetchone()[0])
        for column_name, data_type in table["_types"].items():
            upper = data_type.upper()
            column_ident = _ident(column_name)
            if upper in TEXT_TYPES:
                samples = _text_samples(con, ident, column_ident)
                if samples:
                    table["columns"][column_name]["samples"] = samples
            elif upper in DATE_TYPES:
                low, high = con.execute(
                    f"SELECT min({column_ident}), max({column_ident}) FROM {ident}"
                ).fetchone()
                if low is not None and high is not None:
                    table["columns"][column_name]["samples"] = [_plain(low), _plain(high)]
        del table["_types"]
    return grouped


def _text_samples(con, table_ident: str, column_ident: str) -> list[str]:
    rows = con.execute(
        f"""
        SELECT {column_ident} AS value, count(*) AS n
        FROM {table_ident}
        WHERE {column_ident} IS NOT NULL
        GROUP BY 1
        ORDER BY n DESC
        LIMIT {LOW_CARDINALITY_MAX + 1}
        """
    ).fetchall()
    if not rows or len(rows) > LOW_CARDINALITY_MAX:
        return []
    return [_clean(row[0]) for row in rows[:SAMPLE_LIMIT]]


def _declared_links(con) -> list[dict]:
    links = []
    for table_name, kind, column_names, referenced_table, referenced_columns in db.fetch_constraints(con):
        if kind != "FOREIGN KEY":
            continue
        cols = list(column_names or [])
        refs = list(referenced_columns or [])
        if len(cols) != 1 or not referenced_table or len(refs) != 1:
            continue
        links.append(
            {
                "primary_key": f"{referenced_table}.{refs[0]}",
                "foreign_key": f"{table_name}.{cols[0]}",
                "status": "declared",
                "confidence": 1.0,
                "reason": "declared",
                "needs_review": False,
            }
        )
    return links


def _guess_links(con, tables_meta: dict, declared: list[dict]) -> list[dict]:
    declared_keys = {(item["foreign_key"], item["primary_key"]) for item in declared}
    pks = _primary_keys(con)
    fk_candidates = []
    for table_name, meta in tables_meta.items():
        for column_name in meta.get("columns") or {}:
            if column_name.lower().endswith("_id") or column_name.lower() == "id":
                if (table_name, column_name) in pks and column_name.lower() == "id":
                    continue
                if (table_name, column_name) in pks and column_name.lower().endswith("_id"):
                    # Skip own PK like customers.customer_id
                    stem = column_name[:-3] if column_name.lower().endswith("_id") else column_name
                    if _singular(table_name) == stem or table_name.rstrip("s") == stem:
                        continue
                fk_candidates.append((table_name, column_name))

    guesses = []
    for table_name, column_name in fk_candidates:
        targets = _name_targets(table_name, column_name, pks, tables_meta)
        best = None
        for pk_table, pk_column, name_hit in targets:
            fk_key = f"{table_name}.{column_name}"
            pk_key = f"{pk_table}.{pk_column}"
            if (fk_key, pk_key) in declared_keys:
                continue
            overlap = _overlap_ratio(con, table_name, column_name, pk_table, pk_column)
            reasons = []
            if name_hit:
                reasons.append("name_match")
            if overlap is not None and overlap >= MEDIUM_OVERLAP:
                reasons.append("value_subset")
            if not reasons:
                continue
            confidence = _confidence(name_hit, overlap)
            if confidence < 0.4:
                continue
            needs_review = confidence < 0.9
            if confidence >= 0.9 and name_hit and (overlap or 0) >= HIGH_OVERLAP:
                needs_review = False
            candidate = {
                "primary_key": pk_key,
                "foreign_key": fk_key,
                "status": "guessed",
                "confidence": round(confidence, 3),
                "reason": "+".join(reasons),
                "needs_review": needs_review,
            }
            if best is None or candidate["confidence"] > float(best["confidence"]):
                best = candidate
        if best is not None and float(best["confidence"]) >= 0.4:
            if float(best["confidence"]) < 0.55 and "value_subset" not in (best["reason"] or ""):
                continue
            guesses.append(best)
    return guesses


def _confidence(name_hit: bool, overlap: float | None) -> float:
    if name_hit and overlap is not None and overlap >= HIGH_OVERLAP:
        return min(0.99, 0.85 + overlap * 0.14)
    if name_hit and overlap is not None and overlap >= MEDIUM_OVERLAP:
        return 0.75 + (overlap - MEDIUM_OVERLAP) * 0.4
    if name_hit and (overlap is None or overlap < MEDIUM_OVERLAP):
        return 0.55 if overlap is None else 0.45 + overlap * 0.2
    if overlap is not None and overlap >= HIGH_OVERLAP:
        return 0.7
    if overlap is not None and overlap >= MEDIUM_OVERLAP:
        return 0.5
    return 0.2


def _name_targets(
    table_name: str,
    column_name: str,
    pks: set[tuple[str, str]],
    tables_meta: dict,
) -> list[tuple[str, str, bool]]:
    found: list[tuple[str, str, bool]] = []
    lower = column_name.lower()
    if lower.endswith("_id"):
        stem = column_name[:-3]
    elif lower == "id":
        return found
    else:
        stem = column_name

    candidates = []
    plural = _plural(stem)
    singular = _singular(stem)
    for name in tables_meta:
        if name == table_name:
            continue
        name_sing = _singular(name)
        if name in {stem, plural, singular} or name_sing == singular:
            candidates.append(name)
            continue
        # preferred_mechanic_id → mechanics.mechanic_id
        if stem.endswith(name) or stem.endswith(name_sing) or stem.endswith("_" + name_sing):
            candidates.append(name)
            continue
        if name_sing and (stem.endswith("_" + name_sing) or stem == name_sing):
            candidates.append(name)

    for pk_table in candidates:
        for pk_col in (f"{_singular(pk_table)}_id", "id", column_name):
            if (pk_table, pk_col) in pks or pk_col in tables_meta[pk_table]["columns"]:
                found.append((pk_table, pk_col, True))
                break
    # Also try exact column name match on other PKs
    if not found:
        for pk_table, pk_col in pks:
            if pk_table == table_name:
                continue
            if pk_col == column_name:
                found.append((pk_table, pk_col, True))
    return found


def _overlap_ratio(con, fk_table: str, fk_col: str, pk_table: str, pk_col: str) -> float | None:
    try:
        fk_ident = _ident(fk_table)
        fk_c = _ident(fk_col)
        pk_ident = _ident(pk_table)
        pk_c = _ident(pk_col)
        row = con.execute(
            f"""
            SELECT
              (
                SELECT count(*) FROM (
                  SELECT DISTINCT {fk_c} AS v
                  FROM {fk_ident}
                  WHERE {fk_c} IS NOT NULL
                  LIMIT {OVERLAP_SAMPLE}
                ) s
                WHERE EXISTS (
                  SELECT 1 FROM {pk_ident} p WHERE p.{pk_c} = s.v
                )
              ) * 1.0
              /
              NULLIF(
                (
                  SELECT count(*) FROM (
                    SELECT DISTINCT {fk_c} AS v
                    FROM {fk_ident}
                    WHERE {fk_c} IS NOT NULL
                    LIMIT {OVERLAP_SAMPLE}
                  ) s
                ),
                0
              )
            """
        ).fetchone()
        if not row or row[0] is None:
            return None
        return float(row[0])
    except Exception:
        return None


def _primary_keys(con) -> set[tuple[str, str]]:
    found = set()
    for table_name, kind, column_names, _ref_table, _ref_cols in db.fetch_constraints(con):
        if kind != "PRIMARY KEY":
            continue
        cols = list(column_names or [])
        if len(cols) == 1:
            found.add((table_name, cols[0]))
    return found


def _merge_tables(existing: dict, profiled: dict) -> dict:
    merged = {}
    for name, meta in profiled.items():
        old = existing.get(name) or {}
        columns = {}
        old_cols = old.get("columns") or {}
        for col_name, col_meta in (meta.get("columns") or {}).items():
            prior = old_cols.get(col_name)
            note = ""
            if isinstance(prior, dict):
                note = prior.get("note") or ""
            elif isinstance(prior, str):
                note = prior
            columns[col_name] = {
                "note": note,
                "samples": list(col_meta.get("samples") or []),
            }
        # Keep human notes for columns that disappeared? skip.
        merged[name] = {
            "description": old.get("description") or meta.get("description") or "",
            "row_count": meta.get("row_count", 0),
            "columns": columns,
        }
    # Preserve descriptions for tables no longer present? drop them.
    return merged


def _merge_links(existing: list, declared: list[dict], guessed: list[dict]) -> list[dict]:
    by_pair: dict[tuple[str, str], dict] = {}
    for link in existing:
        pk = link.get("primary_key")
        fk = link.get("foreign_key")
        if not pk or not fk:
            continue
        by_pair[(fk, pk)] = dict(link)

    for link in declared:
        key = (link["foreign_key"], link["primary_key"])
        prior = by_pair.get(key)
        if prior and prior.get("status") in {"confirmed", "rejected"}:
            # Keep human decision; still mark reason if was declared
            if prior.get("status") == "confirmed":
                prior = {**link, **prior, "status": "confirmed", "needs_review": False}
            by_pair[key] = prior
        else:
            by_pair[key] = link

    for link in guessed:
        key = (link["foreign_key"], link["primary_key"])
        prior = by_pair.get(key)
        if prior is None:
            by_pair[key] = link
            continue
        if prior.get("status") in {"declared", "confirmed", "rejected"}:
            continue
        # Refresh auto guess fields but keep needs_review false if user already cleared it
        merged = dict(link)
        if prior.get("needs_review") is False and prior.get("status") == "guessed":
            merged["needs_review"] = False
        by_pair[key] = merged

    # Prefer confirmed/declared ordering
    order = {"declared": 0, "confirmed": 1, "guessed": 2, "rejected": 3}
    items = list(by_pair.values())
    items.sort(key=lambda item: (order.get(item.get("status"), 9), item.get("foreign_key") or ""))
    return items


def _ident(name: str) -> str:
    if not IDENT.fullmatch(name):
        raise ValueError(f"Unexpected identifier: {name}")
    return '"' + name + '"'


def _singular(name: str) -> str:
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith("ses"):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


def _plural(name: str) -> str:
    if name.endswith("y") and name[-2:] not in {"ay", "ey", "oy", "uy"}:
        return name[:-1] + "ies"
    if name.endswith("s"):
        return name
    return name + "s"


def _clean(value) -> str:
    return str(value).replace("\n", " ").replace("\r", " ").strip()


def _plain(value) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat(sep=" ") if hasattr(value, "hour") else value.isoformat()
    return str(value)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Profile a registered DuckDB dataset into hints/<id>.json")
    parser.add_argument("--id", required=True)
    args = parser.parse_args()
    document = profile(args.id)
    print(path_for(args.id))
    print(f"tables={len(document.get('tables') or {})} links={len(document.get('links') or [])}")


if __name__ == "__main__":
    main()
