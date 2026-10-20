"""Отчёты о тестах для модели: общие для решателей и инструментов.

Стартовая информация `workflow` и `single_agent` строится одной функцией
`initial_report`, чтобы условия были одинаковыми (docs/spec.md, раздел 12, п. 4).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from debugmas.data.schema import AgentView, TestCase, TestResult
from debugmas.sandbox.runner import truncate_text

FIELD_LIMIT = 1500  # символов на вход/вывод в отчёте
VERDICT_ORDER = ("AC", "WA", "RE", "TLE", "MLE")


def numbered(code: str) -> str:
    lines = code.splitlines()
    width = len(str(len(lines)))
    return "\n".join(f"{i:>{width}} | {line}" for i, line in enumerate(lines, 1))


def verdict_counts(results: Sequence[TestResult] | dict[str, str]) -> dict[str, int]:
    verdicts = results.values() if isinstance(results, dict) else [r.verdict for r in results]
    c = Counter(verdicts)
    return {v: c[v] for v in VERDICT_ORDER if c.get(v)}


def summary_line(results: Sequence[TestResult] | dict[str, str]) -> str:
    counts = verdict_counts(results)
    return ", ".join(f"{n} {v}" for v, n in counts.items()) or "нет тестов"


def select_failing(
    tests: Sequence[TestCase], results: Sequence[TestResult], k: int
) -> list[tuple[TestCase, TestResult]]:
    """`k` упавших тестов с самым коротким входом."""
    by_name = {t.name: t for t in tests}
    failing = [(by_name[r.name], r) for r in results if r.verdict != "AC" and r.name in by_name]
    failing.sort(key=lambda p: (p[0].input_size(), p[0].name))
    return failing[: max(0, k)]


def failing_details(
    tests: Sequence[TestCase],
    results: Sequence[TestResult],
    k: int,
    show_expected: bool = True,
    limit: int = FIELD_LIMIT,
) -> list[dict[str, Any]]:
    out = []
    for t, r in select_failing(tests, results, k):
        d: dict[str, Any] = {
            "name": t.name,
            "verdict": r.verdict,
            "input": truncate_text(t.read_input(), limit),
        }
        if show_expected:
            d["expected"] = truncate_text(t.read_expected(), limit)
        d["got"] = truncate_text(r.stdout, limit)
        d["stderr"] = truncate_text(r.stderr, limit)
        out.append(d)
    return out


def format_test_report(
    tests: Sequence[TestCase],
    results: Sequence[TestResult],
    k: int,
    show_expected: bool = True,
) -> str:
    lines = [f"Всего тестов: {len(results)}. Вердикты: {summary_line(results)}."]
    failed = [r.name for r in results if r.verdict != "AC"]
    if failed:
        shown = ", ".join(f"{r.name}={r.verdict}" for r in results if r.verdict != "AC")
        lines.append(f"Не прошли: {truncate_text(shown, 1500)}")
    for d in failing_details(tests, results, k, show_expected):
        lines.append(f"\n### Тест {d['name']} — {d['verdict']}")
        lines.append(f"Вход:\n```\n{d['input']}\n```")
        if "expected" in d:
            lines.append(f"Ожидаемый вывод:\n```\n{d['expected']}\n```")
        lines.append(f"Вывод программы:\n```\n{d['got']}\n```")
        if d["stderr"].strip():
            lines.append(f"stderr:\n```\n{d['stderr']}\n```")
    return "\n".join(lines)


def initial_report(view: AgentView, k: int, show_expected: bool = True) -> str:
    return format_test_report(view.tests, view.initial_results, k, show_expected)
