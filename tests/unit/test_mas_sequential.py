"""Поведение последовательной MAS на фейковой модели и коротких задачах."""

from __future__ import annotations

import json
import time

from debugmas.solvers.mas.sequential import SequentialMASSolver
from tests.conftest import fixed_code


def answer(code: str, usage: dict | None = None) -> dict:
    item = {"content": f"```python\n{code}```"}
    if usage is not None:
        item["usage"] = usage
    return item


def test_researcher_tool_and_success(make_ctx, load_view):
    script = [
        {"tool_calls": [{"name": "get_test", "arguments": {"name": "01"}}]},
        {"content": "The loop accesses beyond the array bounds."},
        answer(fixed_code("fx001_c")),
    ]
    ctx, llm, sink = make_ctx(script, solver="mas_sequential")
    result = SequentialMASSolver(ctx.config).solve(load_view("fx001_c"), ctx)
    assert result.status == "solved" and result.steps == 3
    assert len(result.attempts) == 1 and result.attempts[0].passed_all
    assert result.tool_calls == {"get_test": 1, "run_tests": 1}
    assert result.usage.calls == 3 and len(llm.calls) == 3  # успешный код не требует LLM-проверки
    assert {e["agent"] for e in sink.events if e["event"] == "llm_call"} == {"researcher", "fixer"}
    llm_events = [e for e in sink.events if e["event"] == "llm_call"]
    assert llm_events[0]["args"]["messages"] == llm.calls[0]["messages"]
    assert llm_events[0]["args"]["tools"] == llm.calls[0]["tools"]
    assert llm.calls[0]["messages"][1]["content"] == llm.calls[2]["messages"][1]["content"]
    assert "accesses beyond" in llm.calls[2]["messages"][-1]["content"]
    assert all(t["function"]["name"] != "submit" for t in llm.calls[0]["tools"])


def test_checker_feedback_reaches_researcher(make_ctx, load_view):
    view = load_view("fx002_a")
    script = [
        {"content": "Check the division."},
        answer(view.code),
        {"content": "Integer division causes WA."},
        {"content": "Use / instead of //."},
        answer(fixed_code("fx002_a")),
    ]
    ctx, llm, sink = make_ctx(script, solver="mas_sequential")
    result = SequentialMASSolver(ctx.config).solve(view, ctx)
    assert result.status == "solved" and [a.passed_all for a in result.attempts] == [False, True]
    assert result.steps == 5 and result.usage.calls == 5
    assert result.attempts[0].usage.calls == 2 and result.attempts[1].usage.calls == 5
    assert "WA" in llm.calls[2]["messages"][1]["content"]
    assert "Integer division" in llm.calls[3]["messages"][-1]["content"]
    assert [e["agent"] for e in sink.events if e["event"] == "attempt"] == ["checker", "checker"]


def test_bad_tool_args_are_returned_to_researcher(make_ctx, load_view):
    script = [
        {"tool_calls": [{"name": "trace", "arguments": "{broken"}]},
        {"content": "Found the cause."},
        answer(fixed_code("fx001_c")),
    ]
    ctx, llm, _ = make_ctx(script, solver="mas_sequential")
    result = SequentialMASSolver(ctx.config).solve(load_view("fx001_c"), ctx)
    assert result.status == "solved" and result.tool_calls["trace"] == 1
    tools = [m for m in llm.calls[1]["messages"] if m["role"] == "tool"]
    assert "JSON" in json.loads(tools[0]["content"])["error"]


def test_missing_code_counts_as_attempt_without_running_tests(make_ctx, load_view):
    ctx, llm, _ = make_ctx(
        [{"content": "Cause"}, {"content": "fix the line"}],
        solver="mas_sequential",
        max_attempts=1,
    )
    result = SequentialMASSolver(ctx.config).solve(load_view("fx001_c"), ctx)
    assert result.status == "attempts_exhausted" and result.steps == 2
    assert result.attempts[0].note == "no_code_block" and result.attempts[0].code is None
    assert "run_tests" not in result.tool_calls and len(llm.calls) == 2


def test_shared_step_and_token_limits(make_ctx, load_view):
    view = load_view("fx002_a")
    script = [
        {"content": "Hypothesis", "usage": {"input": 600}},
        answer(view.code, {"input": 600}),
        {"content": "Verification"},
    ]
    ctx, llm, _ = make_ctx(script, solver="mas_sequential", max_tokens_per_task=1000)
    result = SequentialMASSolver(ctx.config).solve(view, ctx)
    assert result.status == "token_limit" and result.steps == 2
    assert result.usage.input == 1200 and len(llm.calls) == 2

    ctx, llm, _ = make_ctx(script, solver="mas_sequential", max_steps=2)
    result = SequentialMASSolver(ctx.config).solve(view, ctx)
    assert result.status == "step_limit" and result.steps == 2 and len(llm.calls) == 2


def test_attempt_limit_and_timeout(make_ctx, load_view):
    view = load_view("fx002_a")
    script = [
        {"content": "Hypothesis"},
        answer(view.code),
        {"content": "The bug remains"},
        {"content": "New hypothesis"},
        answer(view.code),
    ]
    ctx, llm, _ = make_ctx(script, solver="mas_sequential", max_attempts=2)
    result = SequentialMASSolver(ctx.config).solve(view, ctx)
    assert result.status == "attempts_exhausted" and len(result.attempts) == 2
    assert len(llm.calls) == 5

    ctx, llm, _ = make_ctx(script, solver="mas_sequential", task_timeout_s=1)
    ctx.started = time.monotonic() - 2
    result = SequentialMASSolver(ctx.config).solve(view, ctx)
    assert result.status == "error" and result.error.startswith("task_timeout")
    assert result.steps == 0 and not llm.calls


def test_llm_error_usage(make_ctx, load_view):
    ctx, _, _ = make_ctx([{"error": "down", "usage": {"input": 50}}], solver="mas_sequential")
    result = SequentialMASSolver(ctx.config).solve(load_view("fx001_c"), ctx)
    assert result.status == "error" and result.usage.input == 50
    assert result.usage.failed_calls == 1
