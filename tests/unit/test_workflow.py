from debugmas.solvers.workflow import WorkflowSolver, extract_code
from tests.conftest import fixed_code


def block(code: str) -> dict:
    return {"content": f"Explanation.\n```python\n{code}```"}


def test_extract_last_block():
    text = "```python\na = 1\n```\ntext\n```python\nb = 2\n```"
    assert extract_code(text) == "b = 2\n"
    assert extract_code("```py\nx\n```") == "x\n"
    assert extract_code("no code") is None
    assert extract_code("```\nplain\n```") is None


def test_solved_first_attempt(make_ctx, load_view):
    ctx, llm, sink = make_ctx([block(fixed_code("fx001_a"))])
    res = WorkflowSolver(ctx.config).solve(load_view("fx001_a"), ctx)
    assert res.status == "solved" and len(res.attempts) == 1
    assert res.attempts[0].passed_all and res.final_code == fixed_code("fx001_a")
    assert len(llm.calls) == 1
    user = llm.calls[0]["messages"][1]["content"]
    assert "6 | for i in range(1, n):" in user  # код с номерами строк
    assert "Expected output" in user
    assert any(e["event"] == "attempt" for e in sink.events)


def test_no_block_then_syntax_error_then_success(make_ctx, load_view):
    script = [
        {"content": "I will fix it later"},
        {"content": "```python\nn = int(input(\n```"},
        block(fixed_code("fx001_b")),
    ]
    ctx, llm, _ = make_ctx(script)
    res = WorkflowSolver(ctx.config).solve(load_view("fx001_b"), ctx)
    assert res.status == "solved"
    assert [a.note for a in res.attempts] == ["no_code_block", "syntax_error", None]
    assert res.attempts[0].code is None
    retry1 = llm.calls[1]["messages"][-1]["content"]
    assert "No code block was found" in retry1
    assert "syntax error" in llm.calls[2]["messages"][-1]["content"]


def test_success_on_second_attempt_and_per_attempt_usage(make_ctx, load_view):
    view = load_view("fx002_a")
    script = [
        {**block(view.code), "usage": {"input": 100, "output": 10}},
        {**block(fixed_code("fx002_a")), "usage": {"input": 300, "output": 20}},
    ]
    ctx, llm, _ = make_ctx(script)
    res = WorkflowSolver(ctx.config).solve(view, ctx)
    assert res.status == "solved"
    assert [a.passed_all for a in res.attempts] == [False, True]
    assert [(a.usage.input, a.usage.output) for a in res.attempts] == [(100, 10), (300, 20)]
    assert (res.usage.input, res.usage.output) == (400, 30)
    # повтор содержит последний вариант кода и новый отчёт
    retry = llm.calls[1]["messages"][-1]["content"]
    assert "print(s // n)" in retry and "Verdicts" in retry


def test_attempts_exhausted(make_ctx, load_view):
    view = load_view("fx001_c")
    ctx, _, _ = make_ctx([block(view.code)] * 5, max_attempts=2)
    res = WorkflowSolver(ctx.config).solve(view, ctx)
    assert res.status == "attempts_exhausted" and len(res.attempts) == 2
    assert res.final_code == view.code


def test_token_limit(make_ctx, load_view):
    script = [{"content": "no", "usage": {"input": 900, "output": 200}}] * 3
    ctx, _, _ = make_ctx(script, max_tokens_per_task=1000)
    res = WorkflowSolver(ctx.config).solve(load_view("fx001_c"), ctx)
    assert res.status == "token_limit" and len(res.attempts) == 1
    assert res.usage.total == 1100


def test_llm_error_counts_tokens(make_ctx, load_view):
    ctx, _, _ = make_ctx([{"error": "down", "usage": {"input": 50}}])
    res = WorkflowSolver(ctx.config).solve(load_view("fx001_c"), ctx)
    assert res.status == "error" and "down" in res.error
    assert res.usage.input == 50 and res.usage.failed_calls == 1
