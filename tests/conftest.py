import json
import warnings

import httpx
import pytest

from biasprobe.config import AppConfig, ModelConfig, ServerConfig
from biasprobe.demo_data import load_demo
from biasprobe.storage import Storage

warnings.filterwarnings("ignore", category=UserWarning)


@pytest.fixture
def storage():
    s = Storage(":memory:")
    yield s
    s.close()


@pytest.fixture
def demo_storage(storage):
    load_demo(storage)
    return storage


def make_cfg(tmp_path, style="openai_chat", **server_kw) -> AppConfig:
    cfg = AppConfig(
        server=ServerConfig(base_url="http://llm.test/v1", api_style=style, max_retries=2, **server_kw),
        models=[ModelConfig(name="model-a"), ModelConfig(name="model-b", params={"temperature": 0.2})],
        config_dir=tmp_path,
    )
    cfg.generation.stories_per_prompt = 1
    cfg.judge.model = "model-a"
    return cfg


@pytest.fixture
def cfg(tmp_path):
    return make_cfg(tmp_path)


class FakeServer:
    """httpx mock transport that behaves like an OpenAI-compatible chat server."""

    def __init__(self, reply=None, fail_first=0, status=500):
        self.requests: list[dict] = []
        self.reply = reply or (lambda body: f"Story for {body['model']}: " + "word " * 40)
        self.fail_first = fail_first
        self.status = status
        self.calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        body = json.loads(request.content or b"{}")
        self.requests.append({"url": str(request.url), "headers": dict(request.headers), "body": body})
        if self.calls <= self.fail_first:
            return httpx.Response(self.status, json={"error": "boom"})
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "model-a"}, {"id": "model-b"}]})
        text = self.reply(body)
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": text}}],
                                         "usage": {"total_tokens": 42}})

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)
