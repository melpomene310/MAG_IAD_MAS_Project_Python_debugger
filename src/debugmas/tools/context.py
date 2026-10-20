"""Состояние сессии инструментов для одной задачи."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from debugmas.data.schema import AgentView, TestCase, TestResult
from debugmas.sandbox.runner import run_tests


@dataclass
class Submission:
    code: str
    verdicts: dict[str, str]
    passed_all: bool
    wall_time_s: float


@dataclass
class ToolContext:
    view: AgentView
    failing_shown: int = 2
    show_expected: bool = True
    max_chars: int = 3000
    memory_mb: int = 1024
    workers: int = 8
    trace_max_hits: int = 30
    max_submissions: int = 3
    submissions: list[Submission] = field(default_factory=list)
    sandbox_time_s: float = 0.0

    @property
    def solved(self) -> bool:
        return any(s.passed_all for s in self.submissions)

    @property
    def submissions_left(self) -> int:
        return self.max_submissions - len(self.submissions)

    def resolve_code(self, code: str | None) -> str:
        return self.view.code if code is None else code

    def run_all(self, code: str, tests: list[TestCase] | None = None) -> list[TestResult]:
        start = time.monotonic()
        try:
            return run_tests(
                code,
                tests if tests is not None else self.view.tests,
                workers=self.workers,
                memory_mb=self.memory_mb,
            )
        finally:
            self.sandbox_time_s += time.monotonic() - start

    def default_time_limit(self) -> float:
        return max((t.time_limit_s for t in self.view.tests), default=2.0)
