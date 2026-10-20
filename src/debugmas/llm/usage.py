"""Учёт использования токенов (docs/spec.md, раздел 7).

Отсутствующее измерение не заменяется ни нулём, ни оценкой: считается известный расход и
отдельно — число запросов, для которых сервер не вернул usage.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class Usage:
    input: int = 0  # все входные токены, включая кэшированные провайдером
    output: int = 0  # все выходные, включая токены рассуждений
    reasoning: int = 0  # часть output
    cached_input: int = 0  # часть input, оплачиваемая по тарифу кэша
    calls: int = 0  # успешные запросы
    failed_calls: int = 0  # неудачные запросы (в т.ч. повторы)
    calls_without_usage: int = 0  # успешные запросы, по которым usage неизвестен
    failed_without_usage: int = 0  # неудачные запросы с неизвестным расходом
    cache_hits: int = 0  # ответы из нашего дискового кэша

    @property
    def total(self) -> int:
        return self.input + self.output

    @property
    def uncached_input(self) -> int:
        return self.input - self.cached_input

    @property
    def unknown_requests(self) -> int:
        return self.calls_without_usage + self.failed_without_usage

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            **{f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)}
        )

    def __sub__(self, other: Usage) -> Usage:
        return Usage(
            **{f.name: getattr(self, f.name) - getattr(other, f.name) for f in fields(self)}
        )

    def cost(self, price_input: float, price_cached_input: float, price_output: float) -> float:
        """Стоимость по тарифам за 1M токенов: вход без кэша + кэшированный вход + выход."""
        return (
            self.uncached_input * price_input
            + self.cached_input * price_cached_input
            + self.output * price_output
        ) / 1e6

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["total"] = self.total
        return d

    def short(self) -> dict[str, int]:
        return {"input": self.input, "output": self.output, "reasoning": self.reasoning}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> Usage:
        if not d:
            return cls()
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


def _get(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def parse_usage(raw: Any) -> Usage | None:
    """Usage из `response.usage` (объект SDK или dict). None, если сервер его не вернул."""
    if raw is None:
        return None
    prompt = _get(raw, "prompt_tokens")
    completion = _get(raw, "completion_tokens")
    if prompt is None and completion is None:
        return None
    reasoning = _get(_get(raw, "completion_tokens_details"), "reasoning_tokens") or 0
    cached = _get(_get(raw, "prompt_tokens_details"), "cached_tokens")
    if cached is None:
        cached = _get(raw, "prompt_cache_hit_tokens")  # DeepSeek
    return Usage(
        input=int(prompt or 0),
        output=int(completion or 0),
        reasoning=int(reasoning or 0),
        cached_input=int(cached or 0),
        calls=1,
    )


def usage_to_dict(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    dump = getattr(raw, "model_dump", None)
    return dump() if dump else None
