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
            raise ToolArgumentError(f"tests do not exist: {missing[:10]}")
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
    return ", ".join(f"{n} {v}" for v, n in result.get("summary", {}).items()) or "no tests"


register(
    Tool(
        name="run_tests",
        description=(
            "Run a program on task tests. Returns verdict counts (AC/WA/RE/TLE/MLE), failed test "
            "names, and input, expected output, and actual output for several shortest failures. "
            "Without `code`, tests the original program."
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Complete program source"},
                "tests": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Test names; all tests by default",
                },
            },
        },
        fn=run_tests,
        summarize=_summary,
    )
)
