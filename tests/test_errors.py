from nlq.errors import friendly


def test_beautifies_llm_503():
    raw = (
        'LLM returned 503: [{"error": {"code": 503, "message": '
        '"This model is currently experiencing high demand. Spikes in demand are usually temporary."}}]'
    )
    nice = friendly(raw)
    assert nice["title"] == "Model is busy"
    assert "high demand" in nice["detail"].lower() or "ask again" in nice["detail"].lower()


def test_beautifies_api_key_errors():
    nice = friendly('LLM returned 400: Please pass a valid API key')
    assert nice["title"] == "API key problem"
