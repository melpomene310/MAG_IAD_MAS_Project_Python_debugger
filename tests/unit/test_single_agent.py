import json

from debugmas.solvers.single_agent import SingleAgentSolver
from tests.conftest import fixed_code


def call(tool: str, **args) -> dict:
    return {"tool_calls": [{"name": tool, "arguments": args}]}


def tool_results(llm, call_idx: int) -> list[dict]:
    msgs = llm.calls[call_idx]["messages"]
    return [json.loads(m["content"]) for m in msgs if m["role"] == "tool"]


def test_accepted_submit(make_ctx, load_view):
    ctx, llm, sink = make_ctx(
        [call("run_tests"), call("submit", code=fixed_code("fx001_c"))], solver="single_agent"
    )
    res = SingleAgentSolver(ctx.config).solve(load_view("fx001_c"), ctx)
    assert res.status == "solved" and res.steps == 2
    assert res.tool_calls == {"run_tests": 1, "submit": 1}
    assert res.attempts[0].passed_all and res.final_code == fixed_code("fx001_c")
    assert res.attempts[0].usage.calls == 2  # накопленное с начала сессии
    assert llm.calls[0]["tools"] and len(llm.calls[0]["tools"]) == 5
    run = tool_results(llm, 1)[0]
    assert run["summary"] == {"RE": 3} and not run["passed_all"]
    assert any(e["event"] == "tool_call" and e["agent"] == "single_agent" for e in sink.events)


def test_same_start_message_as_workflow(make_ctx, load_view):
    from debugmas.solvers.workflow import WorkflowSolver

    view = load_view("fx001_c")
    ctx1, llm1, _ = make_ctx([{"content": "x"}], max_attempts=1)
    WorkflowSolver(ctx1.config).solve(view, ctx1)
    ctx2, llm2, _ = make_ctx([], solver="single_agent", max_steps=1)
    SingleAgentSolver(ctx2.config).solve(view, ctx2)
    assert llm1.calls[0]["messages"][1] == llm2.calls[0]["messages"][1]


def test_bad_tool_args_returned_to_model(make_ctx, load_view):
    script = [
        call("trace", test="01", expressions=["n"]),  # нет lines
        {"tool_calls": [{"name": "run_program", "arguments": "{broken"}]},
        call("get_test", name="nope"),
        call("no_such_tool"),
        call("trace", test="01", input="1", lines=[1], expressions=["n"]),
        call("submit", code=fixed_code("fx001_c")),
    ]
    ctx, llm, _ = make_ctx(script, solver="single_agent")
    res = SingleAgentSolver(ctx.config).solve(load_view("fx001_c"), ctx)
    assert res.status == "solved"
    errors = [r["error"] for r in tool_results(llm, 5) if "error" in r]
    assert len(errors) == 5
    assert "lines" in errors[0] and "JSON" in errors[1] and "nope" in errors[2]
    assert "неизвестный инструмент" in errors[3] and "ровно одно" in errors[4]


def test_text_answer_gets_reminder(make_ctx, load_view):
    script = [{"content": "думаю..."}, call("submit", code=fixed_code("fx001_c"))]
    ctx, llm, sink = make_ctx(script, solver="single_agent")
    res = SingleAgentSolver(ctx.config).solve(load_view("fx001_c"), ctx)
    assert res.status == "solved" and res.steps == 2
    last = llm.calls[1]["messages"][-1]
    assert last["role"] == "user" and "без вызова инструмента" in last["content"]
    assert any(e["event"] == "reminder" for e in sink.events)


def test_rejected_submits_exhaust_attempts(make_ctx, load_view):
    view = load_view("fx001_c")
    ctx, llm, _ = make_ctx(
        [call("submit", code=view.code)] * 5, solver="single_agent", max_attempts=2
    )
    res = SingleAgentSolver(ctx.config).solve(view, ctx)
    assert res.status == "attempts_exhausted" and len(res.attempts) == 2
    first = tool_results(llm, 1)[0]
    assert first["accepted"] is False and first["submissions_left"] == 1


def test_step_limit(make_ctx, load_view):
    ctx, _, _ = make_ctx([call("run_tests")] * 10, solver="single_agent", max_steps=3)
    res = SingleAgentSolver(ctx.config).solve(load_view("fx001_c"), ctx)
    assert res.status == "step_limit" and res.steps == 3


def test_token_limit(make_ctx, load_view):
    script = [{**call("get_test", name="01"), "usage": {"input": 600, "output": 0}}] * 5
    ctx, _, _ = make_ctx(script, solver="single_agent", max_tokens_per_task=1000)
    res = SingleAgentSolver(ctx.config).solve(load_view("fx001_c"), ctx)
    assert res.status == "token_limit" and res.steps == 2


def test_llm_error(make_ctx, load_view):
    ctx, _, _ = make_ctx([call("get_test", name="01"), {"error": "x"}], solver="single_agent")
    res = SingleAgentSolver(ctx.config).solve(load_view("fx001_c"), ctx)
    assert res.status == "error" and res.usage.failed_calls == 1


def test_context_compaction(make_ctx, load_view):
    script = [call("run_tests")] + [call("get_test", name="01")] * 8
    ctx, llm, _ = make_ctx(script, solver="single_agent", max_steps=9, context_keep_steps=6)
    SingleAgentSolver(ctx.config).solve(load_view("fx001_c"), ctx)
    # перед 8-м вызовом прошло 7 шагов: результат шага 1 сокращён, шага 2 — ещё нет
    tools7 = [m["content"] for m in llm.calls[7]["messages"] if m["role"] == "tool"]
    assert tools7[0].startswith("[результат run_tests:") and "сокращено" in tools7[0]
    assert "RE" in tools7[0]
    assert tools7[1].startswith("{")
    tools6 = [m["content"] for m in llm.calls[6]["messages"] if m["role"] == "tool"]
    assert tools6[0].startswith("{")


def test_tools_subset(make_ctx, load_view):
    ctx, llm, _ = make_ctx(
        [call("trace", test="01", lines=[1], expressions=["1"])],
        solver="single_agent",
        tools=["run_tests", "submit"],
        max_steps=1,
    )
    SingleAgentSolver(ctx.config).solve(load_view("fx001_c"), ctx)
    names = [t["function"]["name"] for t in llm.calls[0]["tools"]]
    assert names == ["run_tests", "submit"]
