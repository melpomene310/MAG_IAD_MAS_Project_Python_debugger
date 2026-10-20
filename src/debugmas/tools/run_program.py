"""Инструмент `run_program`: запуск программы на произвольном входе."""

from __future__ import annotations

import time
from typing import Any

from debugmas.sandbox.runner import run_program as sandbox_run
from debugmas.sandbox.runner import truncate_text
from debugmas.tools.context import ToolContext
from debugmas.tools.registry import Tool, register

OUTPUT_LIMIT = 1500


def run_program(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    code = ctx.resolve_code(args.get("code"))
    start = time.monotonic()
    try:
        res = sandbox_run(code, args["input"], ctx.default_time_limit(), ctx.memory_mb)
    finally:
        ctx.sandbox_time_s += time.monotonic() - start
    return {
        "stdout": truncate_text(res.stdout, OUTPUT_LIMIT),
        "stderr": truncate_text(res.stderr, OUTPUT_LIMIT),
        "exit_code": res.exit_code,
        "timed_out": res.timed_out,
        "memory_exceeded": res.memory_exceeded,
        "time_s": res.wall_time,
    }


register(
    Tool(
        name="run_program",
        description=(
            "Запустить программу на своём входе (stdin). Возвращает stdout, stderr, код возврата "
            "и время. Без `code` запускается исходная программа."
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Полный текст программы"},
                "input": {"type": "string", "description": "Данные для stdin"},
            },
            "required": ["input"],
        },
        fn=run_program,
        summarize=lambda r: f"exit {r.get('exit_code')}",
    )
)
