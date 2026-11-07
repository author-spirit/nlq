"""Turn raw engine and LLM failures into short user-facing copy."""

from __future__ import annotations

import json
import re


def friendly(message: str | None) -> dict | None:
    if not message:
        return None
    text = str(message).strip()
    lower = text.lower()
    if "503" in text or "high demand" in lower or "unavailable" in lower:
        return {
            "title": "Model is busy",
            "detail": "The language model is under high demand right now. Wait a moment and ask again.",
        }
    if "401" in text or "api key" in lower or "valid api key" in lower:
        return {
            "title": "API key problem",
            "detail": "Check the active provider key in your .env file, then restart the server.",
        }
    if "404" in text and "model" in lower:
        return {
            "title": "Model not found",
            "detail": "The configured model name is not available. Update the model in .env.",
        }
    if "timeout" in lower or "exceeded" in lower:
        return {
            "title": "Query timed out",
            "detail": "The SQL ran too long. Narrow the question or add a tighter filter.",
        }
    if "deny" in lower or "not allowed" in lower or "only select" in lower:
        return {
            "title": "Query blocked",
            "detail": "Only read-only SELECT queries are allowed.",
        }
    detail = _shorten(text)
    return {"title": "Something went wrong", "detail": detail}


def _shorten(text: str) -> str:
    match = re.search(r"LLM returned \d+:\s*(.*)$", text, re.DOTALL)
    if match:
        body = match.group(1).strip()
        try:
            payload = json.loads(body)
            extracted = _from_json(payload)
            if extracted:
                return extracted
        except json.JSONDecodeError:
            pass
        return body[:240]
    return text[:240]


def _from_json(payload) -> str | None:
    if isinstance(payload, list) and payload:
        return _from_json(payload[0])
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:240]
        if isinstance(err, str):
            return err[:240]
        if payload.get("message"):
            return str(payload["message"])[:240]
    return None
