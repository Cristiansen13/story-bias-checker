import httpx
import pytest

from biasprobe.config import ModelConfig, ServerConfig
from biasprobe.llm_client import LLMClient, LLMError, _render

from conftest import FakeServer


def test_openai_chat_roundtrip(cfg, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "secret")
    fake = FakeServer()
    with LLMClient(cfg.server, transport=fake.transport(), sleep=lambda s: None) as client:
        resp = client.complete(cfg.models[1], "Tell a story", system="sys", max_tokens=50, temperature=0.9)
    assert resp.text.startswith("Story for model-b")
    assert resp.usage == {"total_tokens": 42}
    req = fake.requests[0]
    assert req["url"] == "http://llm.test/v1/chat/completions"
    assert req["headers"]["authorization"] == "Bearer secret"
    assert req["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert req["body"]["temperature"] == 0.2  # model-level param overrides the call default
    assert req["body"]["max_tokens"] == 50


def test_retries_then_succeeds(cfg):
    fake = FakeServer(fail_first=2, status=503)
    sleeps = []
    with LLMClient(cfg.server, transport=fake.transport(), sleep=sleeps.append) as client:
        resp = client.complete(cfg.models[0], "hi")
    assert resp.attempts == 3 and len(sleeps) == 2


def test_gives_up_after_retries(cfg):
    fake = FakeServer(fail_first=10, status=500)
    with LLMClient(cfg.server, transport=fake.transport(), sleep=lambda s: None) as client:
        with pytest.raises(LLMError, match="failed after 3 attempts"):
            client.complete(cfg.models[0], "hi")


def test_non_retryable_error_raises_immediately(cfg):
    fake = FakeServer(fail_first=10, status=401)
    with LLMClient(cfg.server, transport=fake.transport(), sleep=lambda s: None) as client:
        with pytest.raises(LLMError, match="HTTP 401"):
            client.complete(cfg.models[0], "hi")
    assert fake.calls == 1


def test_custom_style_rendering_and_parsing():
    server = ServerConfig(base_url="http://x.test", api_style="custom", endpoint="/gen",
                          request_json={"m": "{model}", "input": "Q: {prompt}", "n": "{max_tokens}",
                                        "opts": {"t": "{temperature}"}},
                          response_path="result.0.text")
    url, body = LLMClient.build_request(server, ModelConfig("m1"), "hello", None, 99, 0.3)
    assert url == "http://x.test/gen"
    assert body == {"m": "m1", "input": "Q: hello", "n": 99, "opts": {"t": 0.3}}
    text, _ = LLMClient.parse_response(server, {"result": [{"text": "out"}]})
    assert text == "out"
    with pytest.raises(LLMError):
        LLMClient.parse_response(server, {"result": []})


def test_ollama_and_completions_styles():
    server = ServerConfig(base_url="http://o.test", api_style="ollama")
    url, body = LLMClient.build_request(server, ModelConfig("llama"), "p", "s", 10, 0.5)
    assert url == "http://o.test/api/generate" and body["stream"] is False and body["system"] == "s"
    assert LLMClient.parse_response(server, {"response": "x", "eval_count": 3}) == ("x", {"eval_count": 3})
    server = ServerConfig(base_url="http://c.test/v1", api_style="openai_completions")
    url, body = LLMClient.build_request(server, ModelConfig("m"), "p", "s", 10, 0.5)
    assert url == "http://c.test/v1/completions" and body["prompt"] == "s\n\np"


def test_render_keeps_types():
    assert _render({"a": "{n}", "b": "x{n}", "c": ["{n}"]}, {"n": 5}) == {"a": 5, "b": "x5", "c": [5]}
    assert _render("{missing}", {}) == "{missing}"


def test_list_models(cfg):
    fake = FakeServer()
    with LLMClient(cfg.server, transport=fake.transport()) as client:
        assert client.list_models() == ["model-a", "model-b"]
