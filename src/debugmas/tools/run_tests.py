"""Инструмент `run_tests`: прогон тестов и детали первых упавших."""

from __future__ import annotations

from typing import Any

from debugmas.feedback import failing_details, verdict_counts
from debugmas.tools.context import ToolContext
from debugmas.tools.registry import Tool, ToolArgumentError, register

MAX_FAILED_NAMES = 50


def run_tests(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    code = ctx.resolve_code(args.get("code"))
    tests = ctx.view.tests
    if args.get("tests"):
        wanted = list(args["tests"])
        missing = [n for n in wanted if ctx.view.test_by_name(n) is None]
        if missing:
            raise ToolArgumentError(f"нет тестов: {missing[:10]}")
        tests = [t for t in tests if t.name in set(wanted)]
    results = ctx.run_all(code, tests)
    failed = [r.name for r in results if r.verdict != "AC"]
    return {
        "n_tests": len(results),
        "summary": verdict_counts(results),
        "passed_all": not failed,
        "failed_tests": failed[:MAX_FAILED_NAMES],
        "failing_details": failing_details(
            tests, results, ctx.failing_shown, ctx.show_expected, limit=600
        ),
    }


def _summary(result: dict[str, Any]) -> str:
    return ", ".join(f"{n} {v}" for v, n in result.get("summary", {}).items()) or "нет тестов"


register(
    Tool(
        name="run_tests",
        description=(
            "Прогнать программу на тестах задачи. Возвращает сводку вердиктов (AC/WA/RE/TLE/MLE), "
            "имена упавших тестов и вход, ожидаемый и полученный вывод для нескольких самых "
            "коротких упавших тестов. Без `code` проверяется исходная программа."
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Полный текст программы"},
                "tests": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Имена тестов; по умолчанию все",
                },
            },
        },
        fn=run_tests,
        summarize=_summary,
    )
)
