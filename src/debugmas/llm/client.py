"""LLM-клиент: OpenAI-совместимый endpoint, повторы, кэш, учёт токенов (docs/spec.md, раздел 7)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Protocol

import openai

from debugmas.llm.cache import LLMCache, cache_key
from debugmas.llm.usage import Usage, parse_usage, usage_to_dict

log = logging.getLogger(__name__)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON-строка, как вернула модель

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    usage: Usage = field(default_factory=Usage)
    raw_usage: dict[str, Any] | None = None
    cache_hit: bool = False
    latency_s: float = 0.0  # исходная задержка (для попадания в кэш — сохранённая)

    def assistant_message(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            msg["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        return msg

    def to_cache(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "finish_reason": self.finish_reason,
        }


class LLMError(RuntimeError):
    """Вызов так и не удался. `usage` — токены неудачных попыток (если известны)."""

    def __init__(self, message: str, usage: Usage | None = None) -> None:
        super().__init__(message)
        self.usage = usage or Usage()


class HardTimeout(RuntimeError):
    """Запрос не уложился в общий таймаут.

    Таймаут SDK считается между порциями данных, а OpenRouter держит соединение живым,
    пока модель думает, поэтому общий срок ограничивается отдельно.
    """


class ChatModel(Protocol):
    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse: ...


def _tool_calls_from(raw: Any) -> list[ToolCall]:
    out = []
    for i, tc in enumerate(raw or []):
        fn = tc["function"] if isinstance(tc, dict) else tc.function
        name = fn["name"] if isinstance(fn, dict) else fn.name
        args = fn["arguments"] if isinstance(fn, dict) else fn.arguments
        tc_id = (tc.get("id") if isinstance(tc, dict) else tc.id) or f"call_{i}"
        out.append(ToolCall(id=tc_id, name=name, arguments=args or "{}"))
    return out


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, HardTimeout):
        return True
    if isinstance(exc, openai.APITimeoutError | openai.APIConnectionError | openai.RateLimitError):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code == 429 or exc.status_code >= 500
    return False


def _usage_from_error(exc: Exception) -> Usage | None:
    """Usage из тела ответа с ошибкой, если сервер его вернул.

    SDK кладёт в `exc.body` только поле `error`, поэтому читаем полный ответ.
    """
    bodies: list[Any] = []
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            bodies.append(response.json())
        except Exception:  # noqa: BLE001
            pass
    bodies.append(getattr(exc, "body", None))
    for body in bodies:
        if isinstance(body, dict):
            u = parse_usage(body.get("usage"))
            if u is not None:
                return u
    return None


class LLMClient:
    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        temperature: float = 0.0,
        timeout_s: float = 120.0,
        max_retries: int = 5,
        max_output_tokens: int | None = None,
        reasoning: dict[str, Any] | None = None,
        cache: LLMCache | None = None,
        repeat_idx: int = 0,
        backoff_base_s: float = 1.0,
        backoff_max_s: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.max_retries = max_retries
        self.max_output_tokens = max_output_tokens
        self.reasoning = reasoning
        self.cache = cache
        self.repeat_idx = repeat_idx
        self.backoff_base_s = backoff_base_s
        self.backoff_max_s = backoff_max_s
        self.timeout_s = timeout_s
        self._sleep = sleep
        self._client = openai.OpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=0
        )

    def _params(self) -> dict[str, Any]:
        p: dict[str, Any] = {"temperature": self.temperature}
        if self.max_output_tokens:
            p["max_tokens"] = self.max_output_tokens
        if self.reasoning is not None:
            p["extra_body"] = {"reasoning": self.reasoning}
        return p

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse:
        params = self._params()
        key = None
        if self.cache is not None:
            key = cache_key(self.base_url, self.model, messages, tools, params, self.repeat_idx)
            hit = self.cache.get(key)
            if hit is not None:
                return self._from_cache(hit)

        failed = Usage()
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            start = time.monotonic()
            try:
                kwargs: dict[str, Any] = {"model": self.model, "messages": messages, **params}
                if tools:
                    kwargs["tools"] = tools
                resp = self._create(kwargs)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                failed.failed_calls += 1
                known = _usage_from_error(exc)
                if known is not None:
                    failed = failed + Usage(
                        input=known.input,
                        output=known.output,
                        reasoning=known.reasoning,
                        cached_input=known.cached_input,
                    )
                else:
                    failed.failed_without_usage += 1  # расход неизвестен — не заменяем нулём
                if not _is_retryable(exc) or attempt == self.max_retries:
                    break
                delay = min(self.backoff_max_s, self.backoff_base_s * (2**attempt))
                log.warning("LLM: %s; повтор %d через %.1f с", exc, attempt + 1, delay)
                self._sleep(delay)
                continue
            latency = time.monotonic() - start
            result = self._parse(resp, latency)
            result.usage = result.usage + failed
            if self.cache is not None and key is not None:
                self.cache.put(
                    key,
                    result.to_cache(),
                    {"raw": result.raw_usage, "parsed": (result.usage - failed).to_dict()},
                    latency,
                )
            return result
        raise LLMError(f"LLM-вызов не удался: {last_exc!r}", failed)

    def _create(self, kwargs: dict[str, Any]) -> Any:
        """Вызов API с жёстким общим таймаутом."""
        pool = ThreadPoolExecutor(max_workers=1)
        fut = pool.submit(self._client.chat.completions.create, **kwargs)
        try:
            return fut.result(timeout=self.timeout_s)
        except FutureTimeout as exc:
            raise HardTimeout(f"нет ответа за {self.timeout_s:.0f} с") from exc
        finally:
            pool.shutdown(wait=False)

    def _parse(self, resp: Any, latency: float) -> LLMResponse:
        choice = resp.choices[0]
        msg = choice.message
        tool_calls = _tool_calls_from(getattr(msg, "tool_calls", None))
        content = msg.content
        usage = parse_usage(getattr(resp, "usage", None))
        if usage is None:
            # сервер не вернул usage: считаем запрос, токены не выдумываем
            usage = Usage(calls=1, calls_without_usage=1)
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage=usage,
            raw_usage=usage_to_dict(getattr(resp, "usage", None)),
            latency_s=latency,
        )

    @staticmethod
    def _from_cache(hit: dict[str, Any]) -> LLMResponse:
        r = hit["response"]
        u = hit.get("usage") or {}
        usage = Usage.from_dict(u.get("parsed"))
        usage.cache_hits = 1
        return LLMResponse(
            content=r.get("content"),
            tool_calls=_tool_calls_from(r.get("tool_calls")),
            finish_reason=r.get("finish_reason"),
            usage=usage,
            raw_usage=u.get("raw"),
            cache_hit=True,
            latency_s=float(hit.get("latency_s", 0.0)),
        )
