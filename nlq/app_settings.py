"""Small JSON settings file (history retention and similar)."""

from __future__ import annotations

import json
from pathlib import Path

from nlq import db

PATH = db.ROOT / "data" / "sqlite" / "settings.json"
DEFAULTS = {
    "history_retention_days": 30,
}


def load() -> dict:
    if not PATH.exists():
        return dict(DEFAULTS)
    try:
        document = json.loads(PATH.read_text())
    except json.JSONDecodeError:
        return dict(DEFAULTS)
    if not isinstance(document, dict):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update(document)
    return merged


def save(document: dict) -> dict:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    current = load()
    current.update(document)
    days = int(current.get("history_retention_days") or DEFAULTS["history_retention_days"])
    if days < 1:
        raise ValueError("history_retention_days must be at least 1")
    if days > 3650:
        raise ValueError("history_retention_days must be at most 3650")
    current["history_retention_days"] = days
    PATH.write_text(json.dumps(current, indent=2) + "\n")
    return current


def history_retention_days() -> int:
    return int(load().get("history_retention_days") or DEFAULTS["history_retention_days"])
