"""Инструмент `trace`: значения выражений на строках программы."""

from __future__ import annotations

import time
from typing import Any

from debugmas.sandbox.tracer import trace as sandbox_trace
from debugmas.tools.context import ToolContext
from debugmas.tools.registry import Tool, ToolArgumentError, register


def trace(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    code = ctx.resolve_code(args.get("code"))
    has_test, has_input = "test" in args, "input" in args
    if has_test == has_input:
        raise ToolArgumentError("нужно передать ровно одно из 'test' или 'input'")
    if has_test:
        test = ctx.view.test_by_name(args["test"])
        if test is None:
            raise ToolArgumentError(f"нет теста '{args['test']}'")
        stdin: str | bytes = test.input_path.read_bytes()
        limit = test.time_limit_s
    else:
        stdin = args["input"]
        limit = ctx.default_time_limit()
    lines = args["lines"]
    n_lines = len(code.splitlines())
    bad = [n for n in lines if not 1 <= n <= n_lines]
    if not lines or bad:
        raise ToolArgumentError(f"номера строк должны быть в диапазоне 1..{n_lines}: {bad}")
    if not args["expressions"]:
        raise ToolArgumentError("список 'expressions' пуст")
    max_hits = int(args.get("max_hits", ctx.trace_max_hits))
    max_hits = max(1, min(max_hits, 200))
    start = time.monotonic()
    try:
        res = sandbox_trace(code, stdin, lines, args["expressions"], max_hits, limit, ctx.memory_mb)
    finally:
        ctx.sandbox_time_s += time.monotonic() - start
    return res.to_dict(output_limit=800)


register(
    Tool(
        name="trace",
        description=(
            "Трассировка: при каждом проходе через указанные строки (ДО их выполнения) вычисляет "
            "выражения в текущем кадре. Вход — имя теста (`test`) или строка (`input`). "
            "Возвращает список срабатываний {line, hit, values} и вывод программы. "
            "Номера строк с 1. Без `code` трассируется исходная программа."
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Полный текст программы"},
                "test": {"type": "string", "description": "Имя теста для stdin"},
                "input": {"type": "string", "description": "Произвольный stdin"},
                "lines": {"type": "array", "items": {"type": "integer"}},
                "expressions": {"type": "array", "items": {"type": "string"}},
                "max_hits": {"type": "integer", "description": "По умолчанию 30"},
            },
            "required": ["lines", "expressions"],
        },
        fn=trace,
        summarize=lambda r: f"{r.get('n_hits', 0)} срабатываний",
    )
)
