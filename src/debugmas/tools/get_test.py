"""Инструмент `get_test`: вход и ожидаемый вывод теста."""

from __future__ import annotations

from typing import Any

from debugmas.sandbox.runner import truncate_text
from debugmas.tools.context import ToolContext
from debugmas.tools.registry import Tool, ToolArgumentError, register

FIELD_LIMIT = 1200


def get_test(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    test = ctx.view.test_by_name(args["name"])
    if test is None:
        names = [t.name for t in ctx.view.tests]
        raise ToolArgumentError(f"test '{args['name']}' does not exist; available: {names[:30]}")
    inp = test.read_input()
    out: dict[str, Any] = {
        "name": test.name,
        "input": truncate_text(inp, FIELD_LIMIT),
        "input_size": len(inp),
        "time_limit_s": test.time_limit_s,
    }
    if ctx.show_expected:
        exp = test.read_expected()
        out["expected"] = truncate_text(exp, FIELD_LIMIT)
        out["expected_size"] = len(exp)
    return out


register(
    Tool(
        name="get_test",
        description="Get a test's input and expected output by name, truncated with their sizes.",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Test name"}},
            "required": ["name"],
        },
        fn=get_test,
        summarize=lambda r: f"test {r.get('name')}",
    )
)
