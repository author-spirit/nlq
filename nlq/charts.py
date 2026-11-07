"""Validate the model's chart spec and fall back from the result shape."""

from __future__ import annotations

import re

CHART_TYPES = {"bar", "line", "pie", "scatter", "table"}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def choose(columns: list[str], rows: list[list], suggestion: dict | None, question: str = "") -> dict:
    kinds = {
        name: _kind([row[index] for row in rows])
        for index, name in enumerate(columns)
    }
    if _fits(suggestion, kinds, columns, rows):
        return _clean(suggestion)
    hinted = _from_question(question, kinds, columns, rows)
    if hinted is not None:
        return hinted
    return _fallback(kinds, columns, rows)


def _clean(spec: dict) -> dict:
    y = spec.get("y") or []
    if isinstance(y, str):
        y = [y]
    series = spec.get("series")
    return {
        "type": spec.get("type"),
        "x": spec.get("x") or "",
        "y": [str(item) for item in y],
        "series": None if not series else str(series),
    }


def _fits(spec: dict | None, kinds: dict, columns: list[str], rows: list[list]) -> bool:
    if not isinstance(spec, dict) or spec.get("type") not in {"bar", "line", "pie", "scatter"}:
        return False
    cleaned = _clean(spec)
    x = cleaned["x"]
    y = cleaned["y"]
    if x not in columns or not y or any(name not in columns for name in y):
        return False
    if cleaned["series"] and cleaned["series"] not in columns:
        return False
    if cleaned["type"] == "scatter":
        return kinds.get(x) == "number" and len(y) == 1 and kinds.get(y[0]) == "number"
    if any(kinds.get(name) != "number" for name in y):
        return False
    if kinds.get(x) not in {"category", "date"}:
        return False
    if cleaned["type"] == "pie":
        return len(y) == 1 and _distinct(rows, columns.index(x)) <= 6
    if cleaned["type"] == "line":
        return True
    return cleaned["type"] == "bar"


def _from_question(question: str, kinds: dict, columns: list[str], rows: list[list]) -> dict | None:
    text = question.lower()
    wanted = None
    for name in ("scatter", "line", "pie", "bar"):
        if re.search(rf"\b{name}\b", text):
            wanted = name
            break
    if wanted is None:
        return None
    spec = _fallback(kinds, columns, rows)
    if spec["type"] == "table":
        return None
    if wanted == "pie" and spec["type"] in {"bar", "pie"} and _distinct(rows, columns.index(spec["x"])) <= 6:
        spec["type"] = "pie"
        spec["y"] = spec["y"][:1]
        return spec
    if wanted == "bar" and spec["type"] in {"bar", "pie"}:
        spec["type"] = "bar"
        return spec
    if wanted == spec["type"]:
        return spec
    return None


def _fallback(kinds: dict, columns: list[str], rows: list[list]) -> dict:
    dates = [name for name in columns if kinds.get(name) == "date"]
    numbers = [name for name in columns if kinds.get(name) == "number"]
    categories = [name for name in columns if kinds.get(name) == "category"]
    if len(dates) == 1 and len(numbers) >= 1 and not categories:
        return {"type": "line", "x": dates[0], "y": numbers[:1] if len(numbers) == 1 else numbers, "series": None}
    if len(categories) == 1 and len(numbers) >= 1 and not dates:
        x = categories[0]
        chart_type = "pie" if len(numbers) == 1 and _distinct(rows, columns.index(x)) <= 6 else "bar"
        y = numbers[:1] if chart_type == "pie" else numbers
        return {"type": chart_type, "x": x, "y": y, "series": None}
    if len(numbers) >= 2 and not dates and not categories:
        return {"type": "scatter", "x": numbers[0], "y": [numbers[1]], "series": None}
    return {"type": "table", "x": "", "y": [], "series": None}


def _kind(values: list) -> str:
    present = [value for value in values if value is not None and value != ""]
    if not present:
        return "empty"
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in present):
        return "number"
    if all(isinstance(value, str) and _DATE.match(value) for value in present):
        return "date"
    return "category"


def _distinct(rows: list[list], index: int) -> int:
    return len({row[index] for row in rows})
