"""Инструмент `submit`: попытка сдать решение (прогон всех тестов)."""

from __future__ import annotations

import time
from typing import Any

from debugmas.feedback import verdict_counts
from debugmas.tools.context import Submission, ToolContext
from debugmas.tools.registry import Tool, ToolArgumentError, register


def submit(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if ctx.submissions_left <= 0:
        raise ToolArgumentError("попытки сдачи исчерпаны")
    code = args["code"]
    start = time.monotonic()
    results = ctx.run_all(code)
    verdicts = {r.name: r.verdict for r in results}
    passed = all(v == "AC" for v in verdicts.values())
    ctx.submissions.append(Submission(code, verdicts, passed, time.monotonic() - start))
    out: dict[str, Any] = {
        "accepted": passed,
        "summary": verdict_counts(results),
        "attempt": len(ctx.submissions),
        "submissions_left": ctx.submissions_left,
    }
    if not passed:
        out["failed_tests"] = [n for n, v in verdicts.items() if v != "AC"][:50]
    return out


register(
    Tool(
        name="submit",
        description=(
            "Сдать исправленную программу целиком. Прогоняются все тесты; если все AC — решение "
            "принято и сессия завершается. Иначе возвращается сводка вердиктов. "
            "Число попыток ограничено — сначала проверьте решение через run_tests."
        ),
        parameters={
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Полный текст программы"}},
            "required": ["code"],
        },
        fn=submit,
        summarize=lambda r: ", ".join(f"{n} {v}" for v, n in r.get("summary", {}).items()),
    )
)
