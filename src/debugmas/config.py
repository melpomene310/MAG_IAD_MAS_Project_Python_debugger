"""Настройки: `.env` (endpoint, секреты) и YAML-конфиги экспериментов.

Приоритет: аргументы CLI > YAML > `.env`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = REPO_ROOT / "prompts"
CONFIGS_DIR = REPO_ROOT / "configs"


class Settings(BaseSettings):
    """Куда и к какой модели обращаться. Загружается из окружения / `.env`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    openai_base_url: str = "http://host.docker.internal:8000/v1"
    openai_api_key: str = "changeme"
    model: str = "deepseek-v4.1-flash"
    price_input_per_1m: float = 0.0
    price_output_per_1m: float = 0.0
    price_cached_input_per_1m: float | None = None  # None — как обычный вход
    llm_timeout_s: float = 300.0
    llm_max_retries: int = 5
    llm_max_concurrency: int = 4
    llm_cache_enabled: bool = True
    llm_cache_dir: str = ".cache/llm"
    sandbox_python: str = "/usr/local/bin/python"


# Параметры модели, от которых зависят ответы (цены и кэш на них не влияют)
RUN_LLM_KEYS = (
    "model",
    "base_url",
    "temperature",
    "max_output_tokens",
    "reasoning",
    "repeat_idx",
    "fake",
)


class LLMConfig(BaseModel):
    model: str | None = None  # None — из .env
    temperature: float = 0.0
    max_output_tokens: int | None = None
    reasoning: dict[str, Any] | None = None  # OpenRouter: {"enabled": false} и т.п.
    timeout_s: float | None = None
    max_retries: int | None = None
    cache_enabled: bool | None = None
    repeat_idx: int = 0
    fake: bool = False  # фейковая LLM (smoke / тесты)
    fake_script: str | None = None  # YAML со сценариями фейковой LLM


class ExperimentConfig(BaseModel):
    """Всё, что относится к эксперименту. Коммитится в `configs/`."""

    solver: str = "workflow"
    data_dir: str = "data/processed"
    splits_dir: str = "splits"
    split_preset: str = "paper3"
    bins: list[str] | None = None  # фильтр по бинам пресета; None — все
    results_dir: str = "results"

    max_attempts: int = 3  # workflow: попытки; single_agent: max_submissions
    max_steps: int = 30
    max_tokens_per_task: int = 300_000
    task_timeout_s: float = 1800.0

    initial_failing_shown: int = 2
    show_expected_output: bool = True
    tools: list[str] = Field(
        default_factory=lambda: ["run_tests", "get_test", "run_program", "trace", "submit"]
    )
    tool_failing_shown: int = 2
    tool_response_max_chars: int = 3000
    context_keep_steps: int = 6
    trace_max_hits: int = 30

    memory_mb: int = 1024
    sandbox_workers: int = 8
    concurrency: int | None = None  # None — LLM_MAX_CONCURRENCY

    llm: LLMConfig = Field(default_factory=LLMConfig)
    solver_params: dict[str, Any] = Field(default_factory=dict)

    def short_hash(self, llm: dict[str, Any] | None = None) -> str:
        """Хэш для id запуска. `llm` — итоговые параметры модели (`resolve_llm`):
        без них смена MODEL в .env продолжила бы старый запуск с другой моделью."""
        payload: dict[str, Any] = {"config": self.model_dump()}
        if llm is not None:
            payload["llm"] = {k: llm.get(k) for k in RUN_LLM_KEYS}
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:8]


def _deep_update(base: dict[str, Any], upd: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in upd.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_update(out[k], v)
        else:
            out[k] = v
    return out


def parse_overrides(items: list[str] | None) -> dict[str, Any]:
    """`a.b=1` → {"a": {"b": 1}}; значения разбираются как YAML."""
    result: dict[str, Any] = {}
    for item in items or []:
        key, _, raw = item.partition("=")
        node = result
        parts = key.strip().split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = yaml.safe_load(raw)
    return result


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_experiment_config(
    path: str | Path | None, overrides: dict[str, Any] | None = None
) -> ExperimentConfig:
    data: dict[str, Any] = load_yaml(path) if path else {}
    if overrides:
        data = _deep_update(data, overrides)
    return ExperimentConfig.model_validate(data)


def resolve_llm(cfg: ExperimentConfig, settings: Settings) -> dict[str, Any]:
    """Итоговые параметры LLM: YAML поверх `.env`."""
    llm = cfg.llm
    return {
        "model": llm.model or settings.model,
        "base_url": settings.openai_base_url,
        "temperature": llm.temperature,
        "max_output_tokens": llm.max_output_tokens,
        "reasoning": llm.reasoning,
        "timeout_s": llm.timeout_s if llm.timeout_s is not None else settings.llm_timeout_s,
        "max_retries": llm.max_retries if llm.max_retries is not None else settings.llm_max_retries,
        "cache_enabled": (
            llm.cache_enabled if llm.cache_enabled is not None else settings.llm_cache_enabled
        ),
        "cache_dir": settings.llm_cache_dir,
        "repeat_idx": llm.repeat_idx,
        "fake": llm.fake,
        "price_input_per_1m": settings.price_input_per_1m,
        "price_output_per_1m": settings.price_output_per_1m,
        "price_cached_input_per_1m": (
            settings.price_cached_input_per_1m
            if settings.price_cached_input_per_1m is not None
            else settings.price_input_per_1m
        ),
    }


def resolved_config_dict(cfg: ExperimentConfig, settings: Settings) -> dict[str, Any]:
    """Итоговый конфиг запуска без секретов (для `config.resolved.yaml`)."""
    d = cfg.model_dump()
    d["llm_resolved"] = resolve_llm(cfg, settings)
    d["sandbox_python"] = settings.sandbox_python
    return d


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def render(template: str, **values: str) -> str:
    """Подстановка `{{name}}` (код содержит фигурные скобки, поэтому не str.format)."""
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", v)
    return template
