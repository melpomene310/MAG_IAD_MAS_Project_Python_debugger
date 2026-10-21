"""The model-facing interface is English regardless of the Russian CLI and reports."""

from __future__ import annotations

import json
import re

from debugmas.config import PROMPTS_DIR
from debugmas.feedback import format_test_report
from debugmas.tools.context import ToolContext
from debugmas.tools.registry import ToolRegistry

CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def test_prompts_and_tool_schemas_are_english() -> None:
    for prompt in PROMPTS_DIR.glob("*.md"):
        assert not CYRILLIC.search(prompt.read_text(encoding="utf-8")), prompt

    schemas = ToolRegistry(["run_tests", "get_test", "run_program", "trace", "submit"]).schemas()
    assert not CYRILLIC.search(json.dumps(schemas, ensure_ascii=False))


def test_generated_test_feedback_is_english(load_view) -> None:
    view = load_view("fx001_c")
    report = format_test_report(view.tests, view.initial_results, k=1)
    assert "Total tests:" in report
    assert "Expected output:" in report
    assert not CYRILLIC.search(report)

    error = ToolRegistry(["trace"]).call(
        "trace", {"test": "01", "lines": ["5"], "expressions": ["i"]}, ToolContext(view=view)
    )["error"]
    assert "argument" in error and not CYRILLIC.search(error)
