"""One OpenAI-compatible chat call. No LangChain."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]

PROVIDERS = {
    "openai": ("OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY"),
    "gemini": ("GEMINI_BASE_URL", "GEMINI_MODEL", "GEMINI_API_KEY"),
    "claude": ("CLAUDE_BASE_URL", "CLAUDE_MODEL", "CLAUDE_API_KEY"),
    "locallama": ("LOCALLAMA_BASE_URL", "LOCALLAMA_MODEL", "LOCALLAMA_API_KEY"),
}

ANTHROPIC_VERSION = "2023-06-01"
logger = logging.getLogger("nlq.llm")
last_usage: dict = {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}


class LLMError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def complete(messages: list[dict]) -> str:
    provider, base_url, model, api_key = resolve()
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if provider == "claude":
        headers["anthropic-version"] = ANTHROPIC_VERSION
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    _log_prompt(provider, model, messages)
    try:
        return _post(provider, model, url, headers, body)
    except LLMError as exc:
        if exc.status != 400:
            raise
        logger.info("llm retry without response_format after status 400")
        body.pop("response_format", None)
        return _post(provider, model, url, headers, body)


def resolve() -> tuple[str, str, str, str]:
    _load_env_file()
    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if provider not in PROVIDERS:
        known = ", ".join(PROVIDERS)
        raise LLMError(f"LLM_PROVIDER must be one of: {known}.")
    base_key, model_key, api_key_name = PROVIDERS[provider]
    base_url = _unquote(os.environ.get(base_key, ""))
    model = _unquote(os.environ.get(model_key, ""))
    api_key = _unquote(os.environ.get(api_key_name, ""))
    if not base_url or not model:
        raise LLMError(f"{provider} needs {base_key} and {model_key}.")
    if provider != "locallama" and not api_key:
        raise LLMError(f"{provider} needs {api_key_name}.")
    return provider, base_url, model, api_key


def list_providers() -> list[dict]:
    _load_env_file()
    active = os.environ.get("LLM_PROVIDER", "").strip().lower()
    found = []
    for name, (base_key, model_key, api_key_name) in PROVIDERS.items():
        base_url = _unquote(os.environ.get(base_key, ""))
        model = _unquote(os.environ.get(model_key, ""))
        api_key = _unquote(os.environ.get(api_key_name, ""))
        configured = bool(base_url and model and (api_key or name == "locallama"))
        found.append(
            {
                "id": name,
                "label": name,
                "model": model or None,
                "configured": configured,
                "active": name == active,
                "has_key": bool(api_key) or name == "locallama",
            }
        )
    return found


def select_provider(provider: str, model: str | None = None) -> dict:
    _load_env_file()
    name = provider.strip().lower()
    if name not in PROVIDERS:
        known = ", ".join(PROVIDERS)
        raise LLMError(f"LLM_PROVIDER must be one of: {known}.")
    base_key, model_key, api_key_name = PROVIDERS[name]
    if model is not None and str(model).strip():
        os.environ[model_key] = str(model).strip()
    os.environ["LLM_PROVIDER"] = name
    # Validate the new selection before returning.
    resolve()
    return next(item for item in list_providers() if item["id"] == name)


def _log_prompt(provider: str, model: str, messages: list[dict]) -> None:
    logger.info("llm request provider=%s model=%s messages=%s", provider, model, len(messages))
    for index, message in enumerate(messages):
        role = message.get("role") or "?"
        content = message.get("content")
        if content is None:
            content = ""
        logger.info("llm prompt[%s] role=%s\n%s", index, role, content)


def _log_response(provider: str, model: str, status: int, text: str, *, error: bool = False) -> None:
    label = "llm error response" if error else "llm response"
    log = logger.error if error else logger.info
    log("%s provider=%s model=%s status=%s\n%s", label, provider, model, status, text)


def _post(provider: str, model: str, url: str, headers: dict, body: dict) -> str:
    try:
        response = httpx.post(url, headers=headers, json=body, timeout=120)
    except httpx.HTTPError as exc:
        logger.error("llm provider=%s model=%s request failed: %s", provider, model, exc)
        raise LLMError(f"LLM request failed: {exc}") from exc
    if response.status_code >= 400:
        detail = response.text
        _log_response(provider, model, response.status_code, detail, error=True)
        raise LLMError(
            f"LLM returned {response.status_code}: {detail[:500]}",
            status=response.status_code,
        )
    try:
        payload = json.loads(response.text)
        usage = payload.get("usage") or {}
        last_usage["prompt_tokens"] = usage.get("prompt_tokens")
        last_usage["completion_tokens"] = usage.get("completion_tokens")
        last_usage["total_tokens"] = usage.get("total_tokens")
        content = payload["choices"][0]["message"]["content"]
        _log_response(provider, model, response.status_code, content if content is not None else "")
        logger.info(
            "llm usage prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            last_usage["prompt_tokens"],
            last_usage["completion_tokens"],
            last_usage["total_tokens"],
        )
        return content
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        _log_response(provider, model, response.status_code, response.text, error=True)
        raise LLMError("LLM response did not contain message content.") from exc


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _load_env_file() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, _, value = text.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
