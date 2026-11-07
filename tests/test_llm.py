import httpx
import pytest

from nlq.llm import LLMError, complete, resolve


def test_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(LLMError, match="LLM_PROVIDER"):
        resolve()


def test_locallama_allows_an_empty_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "locallama")
    monkeypatch.setenv("LOCALLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("LOCALLAMA_MODEL", "llama3.1")
    monkeypatch.setenv("LOCALLAMA_API_KEY", "")
    provider, _base, model, key = resolve()
    assert provider == "locallama"
    assert model == "llama3.1"
    assert key == ""


def test_quoted_gemini_values_are_unwrapped(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_BASE_URL", '"https://generativelanguage.googleapis.com/v1beta/openai"')
    monkeypatch.setenv("GEMINI_MODEL", '"gemini-3.5-flash"')
    monkeypatch.setenv("GEMINI_API_KEY", '"AQ.example-key"')
    provider, base_url, model, api_key = resolve()
    assert provider == "gemini"
    assert base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert model == "gemini-3.5-flash"
    assert api_key == "AQ.example-key"


def test_openai_requires_a_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        resolve()


def test_retries_when_json_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "locallama")
    monkeypatch.setenv("LOCALLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("LOCALLAMA_MODEL", "llama3.1")
    monkeypatch.setenv("LOCALLAMA_API_KEY", "")
    calls = []

    def fake_post(_url, headers, json, timeout):
        calls.append(dict(json))
        if "response_format" in json:
            return httpx.Response(400, text="response_format unsupported")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{\"sql\":null}"}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    assert complete([{"role": "user", "content": "hi"}]) == '{"sql":null}'
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]


def test_logs_a_503(monkeypatch, caplog):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def fake_post(_url, headers, json, timeout):
        return httpx.Response(503, text='[{"error":{"code":503,"message":"high demand","status":"UNAVAILABLE"}}]')

    monkeypatch.setattr(httpx, "post", fake_post)
    with caplog.at_level("ERROR", logger="nlq.llm"):
        with pytest.raises(LLMError, match="503"):
            complete([{"role": "user", "content": "hi"}])
    assert "provider=gemini" in caplog.text
    assert "model=gemini-3.5-flash" in caplog.text
    assert "status=503" in caplog.text
    assert "high demand" in caplog.text
