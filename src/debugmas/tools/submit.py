"""Инструмент `submit`: попытка сдать решение (прогон всех тестов)."""

from __future__ import annotations

import time
from typing import Any

from debugmas.feedback import verdict_counts
from debugmas.tools.context import Submission, ToolContext
from debugmas.tools.registry import Tool, ToolArgumentError, register


def submit(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if ctx.submissions_left <= 0:
        raise ToolArgumentError("submission attempts are exhausted")
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
            "Submit a complete corrected program. All tests are run; if all are AC, "
            "the solution is "
            "accepted and the session ends. Otherwise returns verdict counts. Submission attempts "
            "are limited; check the solution with run_tests first."
        ),
        parameters={
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Complete program source"}},
            "required": ["code"],
        },
        fn=submit,
        summarize=lambda r: ", ".join(f"{n} {v}" for v, n in r.get("summary", {}).items()),
    )
)
