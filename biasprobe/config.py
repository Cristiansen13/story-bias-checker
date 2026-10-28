"""Configuration loading (TOML) for servers, models, generation and paths."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

ENV_CONFIG_PATH = "BIASPROBE_CONFIG"
DEFAULT_CONFIG_NAME = "config.toml"

API_STYLES = ("openai_chat", "openai_completions", "ollama", "custom")


@dataclass
class ServerConfig:
    base_url: str = "http://localhost:8000/v1"
    api_key_env: str = "LLM_API_KEY"
    api_key: str | None = None
    api_style: str = "openai_chat"
    timeout: float = 180.0
    max_concurrency: int = 4
    max_retries: int = 4
    headers: dict[str, str] = field(default_factory=dict)
    endpoint: str | None = None
    request_json: dict[str, Any] | None = None
    response_path: str | None = None

    def resolve_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        return os.environ.get(self.api_key_env) or None

    def merged(self, override: dict[str, Any] | None) -> "ServerConfig":
        """Return a copy with the given keys overridden (model-level server block)."""
        if not override:
            return self
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        for key, value in override.items():
            if key in data:
                data[key] = value
        return ServerConfig(**data)


@dataclass
class ModelConfig:
    name: str
    label: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    system_prompt: str | None = None
    server: dict[str, Any] | None = None

    @property
    def display(self) -> str:
        return self.label or self.name


@dataclass
class GenerationConfig:
    stories_per_prompt: int = 2
    target_words: int = 250
    max_tokens: int = 700
    temperature: float = 0.9
    categories: list[str] | None = None


@dataclass
class JudgeConfig:
    model: str | None = None
    max_tokens: int = 800
    temperature: float = 0.0


@dataclass
class PathsConfig:
    db: str = "data/biasprobe.db"
    model_dir: str = "data/models"
    reports: str = "reports"


@dataclass
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    models: list[ModelConfig] = field(default_factory=list)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    judge: JudgeConfig = field(default_factory=JudgeConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    config_dir: Path = field(default_factory=Path.cwd)
    source: Path | None = None

    def model(self, name: str) -> ModelConfig:
        for m in self.models:
            if m.name == name or m.label == name:
                return m
        raise KeyError(f"model {name!r} is not defined in the config (known: "
                       f"{[m.name for m in self.models]})")

    def server_for(self, model: ModelConfig) -> ServerConfig:
        return self.server.merged(model.server)

    def resolve(self, path: str | Path) -> Path:
        p = Path(path)
        return p if p.is_absolute() else (self.config_dir / p)

    @property
    def db_path(self) -> Path:
        return self.resolve(self.paths.db)

    @property
    def model_dir(self) -> Path:
        return self.resolve(self.paths.model_dir)

    @property
    def reports_dir(self) -> Path:
        return self.resolve(self.paths.reports)


def _build(cls, data: dict[str, Any] | None):
    data = dict(data or {})
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"unknown keys in [{cls.__name__}]: {sorted(unknown)}")
    return cls(**data)


def config_from_dict(data: dict[str, Any], config_dir: Path | None = None,
                     source: Path | None = None) -> AppConfig:
    server = _build(ServerConfig, data.get("server"))
    if server.api_style not in API_STYLES:
        raise ValueError(f"server.api_style must be one of {API_STYLES}")
    models = [_build(ModelConfig, m) for m in data.get("models", [])]
    names = [m.name for m in models]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate model names in config: {names}")
    return AppConfig(
        server=server,
        models=models,
        generation=_build(GenerationConfig, data.get("generation")),
        judge=_build(JudgeConfig, data.get("judge")),
        paths=_build(PathsConfig, data.get("paths")),
        config_dir=config_dir or Path.cwd(),
        source=source,
    )


def find_config_path(explicit: str | Path | None = None) -> Path | None:
    if explicit:
        return Path(explicit)
    env = os.environ.get(ENV_CONFIG_PATH)
    if env:
        return Path(env)
    candidate = Path.cwd() / DEFAULT_CONFIG_NAME
    return candidate if candidate.exists() else None


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load config.toml. Without a file, return defaults (no models) so that the
    offline parts (annotation UI, training, demo data) still work."""
    resolved = find_config_path(path)
    if resolved is None:
        return AppConfig(config_dir=Path.cwd())
    if not resolved.exists():
        raise FileNotFoundError(f"config file not found: {resolved}")
    with open(resolved, "rb") as fh:
        data = tomllib.load(fh)
    return config_from_dict(data, config_dir=resolved.resolve().parent, source=resolved.resolve())
