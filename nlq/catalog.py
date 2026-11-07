"""Schema, sample values, and hints, formatted as prompt text."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from nlq import db

HINTS_DIR = db.HINTS_DIR
HINTS_PATH = db.HINTS_PATH
SAMPLE_LIMIT = 10
SAMPLE_BEGIN = "<<<SAMPLE_VALUES>>>"
SAMPLE_END = "<<<END_SAMPLE_VALUES>>>"
DATE_TYPES = {"DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP_NS"}
ACTIVE_LINK_STATUSES = {"declared", "guessed", "confirmed"}


@dataclass
class Column:
    name: str
    type: str
    key: str = ""
    comment: str = ""
    references: str = ""


@dataclass
class Table:
    name: str
    description: str = ""
    columns: list[Column] = field(default_factory=list)


@dataclass
class Catalog:
    database: str
    description: str
    tables: list[Table]
    prompt_text: str
    samples: list = field(default_factory=list)
    links: list = field(default_factory=list)

    def table(self, name: str) -> Table | None:
        for item in self.tables:
            if item.name == name:
                return item
        return None

    def table_summaries(self) -> list[dict]:
        return [{"name": table.name, "description": table.description or ""} for table in self.tables]

    def fk_neighbours(self, names: list[str]) -> list[str]:
        chosen = set(names)
        changed = True
        while changed:
            changed = False
            for table in self.tables:
                if table.name not in chosen:
                    continue
                for column in table.columns:
                    ref = column.references or ""
                    if not ref or "." not in ref:
                        continue
                    other = ref.split(".", 1)[0]
                    if other and other not in chosen:
                        chosen.add(other)
                        changed = True
            for link in self.links:
                fk = (link.get("foreign_key") or "").split(".", 1)[0]
                pk = (link.get("primary_key") or "").split(".", 1)[0]
                if fk in chosen and pk and pk not in chosen:
                    chosen.add(pk)
                    changed = True
                if pk in chosen and fk and fk not in chosen:
                    chosen.add(fk)
                    changed = True
        return sorted(chosen)

    def prompt_for(self, names: list[str] | None = None) -> str:
        if not names:
            return self.prompt_text
        wanted = set(names)
        tables = [table for table in self.tables if table.name in wanted]
        samples = [item for item in self.samples if item[0] in wanted]
        links = []
        for link in self.links:
            fk = (link.get("foreign_key") or "").split(".", 1)[0]
            pk = (link.get("primary_key") or "").split(".", 1)[0]
            if fk in wanted and pk in wanted:
                links.append(link)
        return _prompt_text(self.description, tables, samples, links)

    def schema_columns(self, names: list[str] | None = None) -> list[dict]:
        chosen = self.tables if not names else []
        if names:
            for name in names:
                item = self.table(name)
                if item is None:
                    raise KeyError(name)
                chosen.append(item)
        rows = []
        for item in chosen:
            for column in item.columns:
                rows.append(
                    {
                        "table": item.name,
                        "name": column.name,
                        "type": column.type,
                        "key": column.key,
                        "comment": column.comment,
                    }
                )
        return rows


_cached: Catalog | None = None


def load(database: str = "ecommerce", force: bool = False) -> Catalog:
    global _cached
    if _cached is not None and not force and _cached.database == database:
        return _cached
    _cached = build(database)
    return _cached


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def build(database: str = "ecommerce") -> Catalog:
    hints = _hints(database)
    con = db.connect(database)
    try:
        columns = db.fetch_columns(con)
        constraints = db.fetch_constraints(con)
        keys, references = _keys(constraints)
        tables = _tables(columns, keys, references, hints)
    finally:
        con.close()
    # Prompt samples/ranges come only from hints/<id>.json (curated / profiled offline).
    # Live row values are never queried for the LLM prompt.
    _apply_hint_date_ranges(tables, hints)
    samples = _hint_samples(hints, tables)
    links = _active_links(hints.get("links", []), references)
    prompt = _prompt_text(hints.get("description", ""), tables, samples, links)
    return Catalog(
        database=database,
        description=hints.get("description", ""),
        tables=tables,
        prompt_text=prompt,
        samples=samples,
        links=links,
    )


def _hints(database: str) -> dict:
    path = HINTS_DIR / f"{database}.json"
    if path.exists():
        document = json.loads(path.read_text())
        return document if isinstance(document, dict) else {}
    # Legacy monolith hints.json
    if not HINTS_PATH.exists():
        return {}
    document = json.loads(HINTS_PATH.read_text())
    if not isinstance(document, dict):
        return {}
    block = document.get(database, {})
    return block if isinstance(block, dict) else {}


def _keys(constraints: list[tuple]) -> tuple[dict, dict]:
    primary: dict[tuple[str, str], bool] = {}
    references: dict[tuple[str, str], str] = {}
    for table_name, kind, column_names, referenced_table, referenced_columns in constraints:
        names = list(column_names or [])
        if kind == "PRIMARY KEY" and len(names) == 1:
            primary[(table_name, names[0])] = True
        elif kind == "FOREIGN KEY" and len(names) == 1 and referenced_table:
            target_cols = list(referenced_columns or [])
            target = referenced_table
            if target_cols:
                target = f"{referenced_table}.{target_cols[0]}"
            references[(table_name, names[0])] = target
    return primary, references


def _active_links(hint_links: list, references: dict[tuple[str, str], str]) -> list[dict]:
    """Merge DuckDB declared FKs with hints links; skip rejected; prefer confirmed/declared."""
    by_pair: dict[tuple[str, str], dict] = {}
    for (table_name, column_name), target in references.items():
        fk = f"{table_name}.{column_name}"
        pk = target if "." in target else f"{target}.id"
        by_pair[(fk, pk)] = {
            "primary_key": pk,
            "foreign_key": fk,
            "status": "declared",
        }

    for link in hint_links or []:
        if not isinstance(link, dict):
            continue
        status = link.get("status") or "confirmed"
        if status == "rejected":
            # Explicit rejection removes any declared/guessed duplicate from the prompt.
            fk = link.get("foreign_key")
            pk = link.get("primary_key")
            if fk and pk:
                by_pair.pop((fk, pk), None)
            continue
        if status not in ACTIVE_LINK_STATUSES:
            continue
        pk = link.get("primary_key")
        fk = link.get("foreign_key")
        if not pk or not fk:
            continue
        key = (fk, pk)
        prior = by_pair.get(key)
        if prior is None:
            by_pair[key] = {
                "primary_key": pk,
                "foreign_key": fk,
                "status": status,
            }
            continue
        # Prefer confirmed/declared over guessed
        rank = {"declared": 3, "confirmed": 2, "guessed": 1}
        if rank.get(status, 0) >= rank.get(prior.get("status"), 0):
            by_pair[key] = {"primary_key": pk, "foreign_key": fk, "status": status}
    return list(by_pair.values())


def _column_note(raw) -> str:
    if isinstance(raw, dict):
        return str(raw.get("note") or "")
    if raw is None:
        return ""
    return str(raw)


def _tables(columns, primary, references, hints: dict) -> list[Table]:
    table_hints = hints.get("tables", {})
    grouped: dict[str, Table] = {}
    for table_name, column_name, data_type, _nullable, _position in columns:
        table = grouped.get(table_name)
        if table is None:
            meta = table_hints.get(table_name, {})
            table = Table(name=table_name, description=meta.get("description", ""))
            grouped[table_name] = table
        column_notes = table_hints.get(table_name, {}).get("columns", {})
        key = ""
        if primary.get((table_name, column_name)):
            key = "PK"
        elif references.get((table_name, column_name)):
            key = "FK"
        table.columns.append(
            Column(
                name=column_name,
                type=data_type,
                key=key,
                comment=_column_note(column_notes.get(column_name, "")),
                references=references.get((table_name, column_name), ""),
            )
        )
    return [grouped[name] for name in sorted(grouped)]


def _hint_column_meta(hints: dict, table_name: str, column_name: str) -> dict:
    tables = hints.get("tables", {})
    if not isinstance(tables, dict):
        return {}
    table = tables.get(table_name, {})
    if not isinstance(table, dict):
        return {}
    columns = table.get("columns", {})
    if not isinstance(columns, dict):
        return {}
    meta = columns.get(column_name, {})
    return meta if isinstance(meta, dict) else {}


def _hint_sample_list(meta: dict) -> list[str]:
    raw = meta.get("samples") or []
    if not isinstance(raw, list):
        return []
    values = []
    for item in raw[:SAMPLE_LIMIT]:
        if item is None:
            continue
        text = _clean_sample(item)
        if text:
            values.append(text)
    return values


def _hint_samples(hints: dict, tables: list[Table]) -> list[tuple[str, str, list[str]]]:
    """Categorical samples for the prompt — from hints only, never live rows."""
    found = []
    for table in tables:
        for column in table.columns:
            if column.type.upper() in DATE_TYPES:
                continue
            values = _hint_sample_list(_hint_column_meta(hints, table.name, column.name))
            if values:
                found.append((table.name, column.name, values))
    return found


def _apply_hint_date_ranges(tables: list[Table], hints: dict) -> None:
    """Attach min/max range notes from hints date samples (offline profile)."""
    for table in tables:
        for column in table.columns:
            if column.type.upper() not in DATE_TYPES:
                continue
            values = _hint_sample_list(_hint_column_meta(hints, table.name, column.name))
            if len(values) < 2:
                continue
            note = f"range {values[0]} .. {values[-1]}"
            column.comment = f"{column.comment}; {note}" if column.comment else note


def _prompt_text(description: str, tables: list[Table], samples, links: list[dict]) -> str:
    lines: list[str] = []
    if description:
        lines.append(f"-- {description}")
    for link in links:
        pk = link.get("primary_key", "")
        fk = link.get("foreign_key", "")
        if pk and fk:
            lines.append(f"-- {fk} -> {pk}")
    lines.append("")
    for table in tables:
        if table.description:
            lines.append(f"-- {table.name}: {table.description}")
        lines.append(f"CREATE TABLE {table.name} (")
        parts = []
        for column in table.columns:
            piece = f"  {column.name} {column.type}"
            if column.key == "PK":
                piece += " PRIMARY KEY"
            notes = []
            if column.references:
                notes.append(f"references {column.references}")
            if column.comment:
                notes.append(column.comment)
            if notes:
                piece += " -- " + "; ".join(notes)
            parts.append(piece)
        lines.append(",\n".join(parts))
        lines.append(");")
        lines.append("")
    lines.append(SAMPLE_BEGIN)
    for table_name, column_name, values in samples:
        shown = ", ".join("'" + value.replace("'", "''") + "'" for value in values)
        lines.append(f"{table_name}.{column_name}: {shown}")
    lines.append(SAMPLE_END)
    return "\n".join(lines)


def _clean_sample(value: str) -> str:
    text = str(value).replace("\n", " ").replace("\r", " ")
    text = text.replace(SAMPLE_BEGIN, "").replace(SAMPLE_END, "")
    return text.strip()
