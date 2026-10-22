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
        raise ToolArgumentError("pass exactly one of 'test' or 'input'")
    if has_test:
        test = ctx.view.test_by_name(args["test"])
        if test is None:
            raise ToolArgumentError(f"test '{args['test']}' does not exist")
        stdin: str | bytes = test.input_path.read_bytes()
        limit = test.time_limit_s
    else:
        stdin = args["input"]
        limit = ctx.default_time_limit()
    lines = args["lines"]
    n_lines = len(code.splitlines())
    bad = [n for n in lines if not 1 <= n <= n_lines]
    if not lines or bad:
        raise ToolArgumentError(f"line numbers must be in range 1..{n_lines}: {bad}")
    if not args["expressions"]:
        raise ToolArgumentError("'expressions' must not be empty")
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
            "At every visit to specified lines, before they execute, evaluate expressions in the "
            "current frame. Input is a test name (`test`) or custom string (`input`). Returns hits "
            "as {line, hit, values} and program output. Line numbers are one-based. "
            "Without `code`, "
            "traces the original program."
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Complete program source"},
                "test": {"type": "string", "description": "Test name for stdin"},
                "input": {"type": "string", "description": "Custom stdin"},
                "lines": {"type": "array", "items": {"type": "integer"}},
                "expressions": {"type": "array", "items": {"type": "string"}},
                "max_hits": {"type": "integer", "description": "Defaults to 30"},
            },
            "required": ["lines", "expressions"],
        },
        fn=trace,
        summarize=lambda r: f"{r.get('n_hits', 0)} hits",
    )
)
