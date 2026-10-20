"""Фейковая LLM: заранее заданная последовательность ответов (docs/spec.md, раздел 14)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from debugmas.llm.client import LLMError, LLMResponse, ToolCall
from debugmas.llm.usage import Usage

DEFAULT_FAKE_USAGE = {"input": 100, "output": 50}
EXHAUSTED_TEXT = "(fake llm: сценарий исчерпан)"


class FakeLLM:
    """Каждый элемент сценария — dict:

    - `content`: текст ответа;
    - `tool_calls`: список `{name, arguments}` (arguments — dict или строка JSON);
    - `usage`: `{input, output, reasoning}` (по умолчанию 100/50);
    - `error`: строка — вызов падает с LLMError (с usage, если задан).
    """

    def __init__(
        self, script: list[dict[str, Any]], default_usage: dict[str, int] | None = None
    ) -> None:
        self.script = list(script)
        self.default_usage = default_usage or DEFAULT_FAKE_USAGE
        self.calls: list[dict[str, Any]] = []  # что получила модель (для тестов)
        self._pos = 0

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LLMResponse:
        self.calls.append({"messages": json.loads(json.dumps(messages)), "tools": tools})
        if self._pos < len(self.script):
            item = self.script[self._pos]
        else:
            item = {"content": EXHAUSTED_TEXT}
        self._pos += 1
        u = item.get("usage", self.default_usage)
        usage = Usage(
            input=int(u.get("input", 0)),
            output=int(u.get("output", 0)),
            reasoning=int(u.get("reasoning", 0)),
            calls=1,
        )
        if "error" in item:
            usage.calls = 0
            usage.failed_calls = 1
            raise LLMError(str(item["error"]), usage)
        tool_calls = []
        for i, tc in enumerate(item.get("tool_calls") or []):
            args = tc.get("arguments", {})
            if not isinstance(args, str):
                args = json.dumps(args, ensure_ascii=False)
            tool_calls.append(ToolCall(id=f"call_{self._pos}_{i}", name=tc["name"], arguments=args))
        return LLMResponse(
            content=item.get("content"),
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            usage=usage,
            raw_usage={"prompt_tokens": usage.input, "completion_tokens": usage.output},
            latency_s=0.0,
        )


def load_fake_scripts(path: str | Path) -> dict[str, Any]:
    """YAML: `{<solver>: {<task_id> | default: [ответы...]}}`."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def fake_for(scripts: dict[str, Any], solver: str, task_id: str) -> FakeLLM:
    per_solver = scripts.get(solver, {}) or {}
    script = per_solver.get(task_id, per_solver.get("default", []))
    return FakeLLM(script)
