"""HTTP client for the remote LLM suite.

Supports OpenAI-compatible chat and completions endpoints, the native Ollama
API, and a fully custom request/response template for anything else.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import ModelConfig, ServerConfig


class LLMError(RuntimeError):
    """Raised when a request fails after all retries or returns an unusable body."""


@dataclass
class LLMResponse:
    text: str
    model: str
    latency_s: float
    raw: Any = None
    usage: dict[str, Any] | None = None
    attempts: int = 1
    request_params: dict[str, Any] = field(default_factory=dict)


RETRY_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}


def _render(obj: Any, variables: dict[str, Any]) -> Any:
    """Fill {placeholders} in a template structure. A string that is exactly one
    placeholder keeps the type of the variable (numbers stay numbers)."""
    if isinstance(obj, str):
        stripped = obj.strip()
        if stripped.startswith("{") and stripped.endswith("}") and stripped.count("{") == 1:
            key = stripped[1:-1]
            if key in variables:
                return variables[key]
        try:
            return obj.format_map(variables)
        except (KeyError, IndexError, ValueError):
            return obj
    if isinstance(obj, dict):
        return {k: _render(v, variables) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_render(v, variables) for v in obj]
    return obj


def _walk(data: Any, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur[part]
        else:
            raise KeyError(part)
    return cur


def _join(base: str, endpoint: str) -> str:
    if not endpoint:
        return base
    return base.rstrip("/") + "/" + endpoint.lstrip("/")


class LLMClient:
    def __init__(self, server: ServerConfig, transport: httpx.BaseTransport | None = None,
                 sleep=time.sleep):
        self.server = server
        self._sleep = sleep
        self._client = httpx.Client(timeout=server.timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ build
    @staticmethod
    def _headers(server: ServerConfig) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **server.headers}
        key = server.resolve_api_key()
        if key and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    @staticmethod
    def build_request(server: ServerConfig, model: ModelConfig, prompt: str,
                      system: str | None, max_tokens: int, temperature: float,
                      extra: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
        params = {**model.params, **(extra or {})}
        temperature = params.pop("temperature", temperature)
        max_tokens = params.pop("max_tokens", max_tokens)
        system = system if system is not None else model.system_prompt
        style = server.api_style

        if style == "openai_chat":
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            body = {"model": model.name, "messages": messages, "max_tokens": max_tokens,
                    "temperature": temperature, **params}
            return _join(server.base_url, server.endpoint or "chat/completions"), body

        if style == "openai_completions":
            full = f"{system}\n\n{prompt}" if system else prompt
            body = {"model": model.name, "prompt": full, "max_tokens": max_tokens,
                    "temperature": temperature, **params}
            return _join(server.base_url, server.endpoint or "completions"), body

        if style == "ollama":
            body = {"model": model.name, "prompt": prompt, "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens, **params}}
            if system:
                body["system"] = system
            return _join(server.base_url, server.endpoint or "api/generate"), body

        if style == "custom":
            if not server.request_json or not server.response_path:
                raise LLMError("api_style=custom needs server.request_json and server.response_path")
            variables = {"prompt": prompt, "system": system or "", "model": model.name,
                         "max_tokens": max_tokens, "temperature": temperature, **params}
            body = _render(server.request_json, variables)
            return _join(server.base_url, server.endpoint or ""), body

        raise LLMError(f"unsupported api_style {style!r}")

    @staticmethod
    def parse_response(server: ServerConfig, data: Any) -> tuple[str, dict[str, Any] | None]:
        style = server.api_style
        try:
            if style == "openai_chat":
                choice = data["choices"][0]
                text = choice.get("message", {}).get("content")
                if text is None:
                    text = choice.get("text", "")
                return text or "", data.get("usage")
            if style == "openai_completions":
                return data["choices"][0]["text"] or "", data.get("usage")
            if style == "ollama":
                usage = {k: data[k] for k in ("prompt_eval_count", "eval_count") if k in data}
                return data.get("response", "") or "", usage or None
            if style == "custom":
                return str(_walk(data, server.response_path or "")), None
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError(f"could not find generated text in response ({exc!r}): "
                           f"{json.dumps(data)[:400]}") from exc
        raise LLMError(f"unsupported api_style {style!r}")

    # ------------------------------------------------------------------- call
    def complete(self, model: ModelConfig, prompt: str, *, system: str | None = None,
                 max_tokens: int = 700, temperature: float = 0.9,
                 server: ServerConfig | None = None,
                 extra: dict[str, Any] | None = None) -> LLMResponse:
        server = server or self.server
        url, body = self.build_request(server, model, prompt, system, max_tokens, temperature, extra)
        headers = self._headers(server)
        last_error: Exception | None = None
        started = time.perf_counter()
        for attempt in range(1, server.max_retries + 2):
            try:
                resp = self._client.post(url, json=body, headers=headers)
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if resp.status_code in RETRY_STATUSES:
                    last_error = LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                elif resp.status_code >= 400:
                    raise LLMError(f"HTTP {resp.status_code} from {url}: {resp.text[:500]}")
                else:
                    try:
                        data = resp.json()
                    except ValueError as exc:
                        raise LLMError(f"non-JSON response from {url}: {resp.text[:300]}") from exc
                    text, usage = self.parse_response(server, data)
                    return LLMResponse(
                        text=text.strip(), model=model.name,
                        latency_s=time.perf_counter() - started, raw=data, usage=usage,
                        attempts=attempt,
                        request_params={"max_tokens": max_tokens, "temperature": temperature},
                    )
            if attempt <= server.max_retries:
                delay = min(30.0, 1.5 ** attempt) + random.uniform(0, 0.5)
                self._sleep(delay)
        raise LLMError(f"request to {url} failed after {server.max_retries + 1} attempts: {last_error}")

    def list_models(self, server: ServerConfig | None = None) -> list[str]:
        """Best-effort model listing for OpenAI-compatible and Ollama servers."""
        server = server or self.server
        if server.api_style in ("openai_chat", "openai_completions"):
            resp = self._client.get(_join(server.base_url, "models"), headers=self._headers(server))
            resp.raise_for_status()
            return [m["id"] for m in resp.json().get("data", [])]
        if server.api_style == "ollama":
            resp = self._client.get(_join(server.base_url, "api/tags"), headers=self._headers(server))
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        raise LLMError("model listing is not available for api_style=custom")
