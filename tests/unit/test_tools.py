import json

from debugmas.tools.context import ToolContext
from debugmas.tools.registry import ToolRegistry, available_tools, truncate_response


def test_builtin_tools_registered():
    assert set(available_tools()) >= {"run_tests", "get_test", "run_program", "trace", "submit"}
    schemas = ToolRegistry(["trace"]).schemas()
    assert schemas[0]["function"]["parameters"]["required"] == ["lines", "expressions"]


def test_truncation_marks_and_size():
    big = {"a": "x" * 5000, "b": "short", "items": [{"v": "y" * 3000}]}
    out = truncate_response(big, 1000)
    assert out["truncated"] is True and out["original_size"] > 8000
    assert len(json.dumps(out, ensure_ascii=False)) <= 1100
    assert out["b"] == "short"
    assert truncate_response({"a": 1}, 1000) == {"a": 1}


def test_type_validation(load_view):
    ctx = ToolContext(view=load_view("fx001_c"))
    reg = ToolRegistry(["trace", "get_test", "run_program"])
    r = reg.call("trace", {"test": "01", "lines": ["3"], "expressions": ["a"]}, ctx)
    assert "integer" in r["error"]
    r = reg.call("get_test", {"name": "01", "extra": 1}, ctx)
    assert "неизвестные аргументы" in r["error"]
    r = reg.call("trace", {"test": "01", "lines": [99], "expressions": ["a"]}, ctx)
    assert "диапазоне" in r["error"]


def test_run_program_and_get_test(load_view):
    ctx = ToolContext(view=load_view("fx001_c"))
    reg = ToolRegistry(["get_test", "run_program", "run_tests"])
    r = reg.call("run_program", {"input": "2\n3 9\n"}, ctx)
    assert r["exit_code"] == 1 and "IndexError" in r["stderr"]
    t = reg.call("get_test", {"name": "01"}, ctx)
    assert t["input"] == "3\n1 5 2\n" and t["expected"] == "5\n"
    rt = reg.call("run_tests", {"tests": ["02"]}, ctx)
    assert rt["n_tests"] == 1 and rt["failing_details"][0]["name"] == "02"
    assert ctx.sandbox_time_s > 0


def test_hidden_expected_output(load_view):
    ctx = ToolContext(view=load_view("fx001_c"), show_expected=False)
    reg = ToolRegistry(["get_test", "run_tests"])
    assert "expected" not in reg.call("get_test", {"name": "01"}, ctx)
    assert "expected" not in reg.call("run_tests", {}, ctx)["failing_details"][0]


def test_trace_tool(load_view):
    ctx = ToolContext(view=load_view("fx001_c"))
    r = ToolRegistry(["trace"]).call(
        "trace", {"test": "01", "lines": [5], "expressions": ["i", "best"]}, ctx
    )
    assert r["hits"][0]["values"] == {"i": "1", "best": "1"}
    assert r["finished"] == "exception"


def test_submit_limit(load_view):
    view = load_view("fx001_c")
    ctx = ToolContext(view=view, max_submissions=1)
    reg = ToolRegistry(["submit"])
    assert reg.call("submit", {"code": view.code}, ctx)["accepted"] is False
    assert "исчерпаны" in reg.call("submit", {"code": view.code}, ctx)["error"]
