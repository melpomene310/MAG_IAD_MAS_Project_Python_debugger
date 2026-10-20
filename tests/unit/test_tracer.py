from debugmas.sandbox.tracer import trace

LOOP = "n = int(input())\ns = 0\nfor i in range(n):\n    s += i\nprint(s)\n"


def test_values_before_line_execution():
    r = trace(LOOP, "3\n", [4], ["i", "s"])
    assert [h["values"] for h in r.hits] == [
        {"i": "0", "s": "0"},
        {"i": "1", "s": "0"},
        {"i": "2", "s": "1"},
    ]
    assert [h["hit"] for h in r.hits] == [1, 2, 3]
    assert r.stdout == "3\n" and r.finished == "finished" and r.exit_code == 0


def test_max_hits():
    r = trace(LOOP, "100\n", [4], ["i"], max_hits=5)
    assert len(r.hits) == 5 and r.max_hits_reached
    assert r.stdout == "4950\n"  # программа доработала до конца


def test_expression_errors_are_values():
    r = trace(LOOP, "1\n", [4], ["zz", "1/0"])
    vals = r.hits[0]["values"]
    assert vals["zz"].startswith("<NameError")
    assert vals["1/0"].startswith("<ZeroDivisionError")


def test_repr_truncated():
    r = trace("x = list(range(1000))\ny = 1\n", "", [2], ["x"])
    assert len(r.hits[0]["values"]["x"]) <= 203


def test_threads_traced():
    code = (
        "import threading\ndef f():\n    x = 5\n    print(x)\nthreading.Thread(target=f).start()\n"
    )
    r = trace(code, "", [4], ["x"])
    assert r.hits and r.hits[0]["values"]["x"] == "5"
    assert r.stdout == "5\n"


def test_exit_terminates_cleanly():
    r = trace("x = 1\nexit()\nprint(x)\n", "", [2, 3], ["x"])
    assert [h["line"] for h in r.hits] == [2]
    assert r.finished == "exit" and r.exit_code == 0


def test_program_exception():
    r = trace("a = [1]\nprint(a[5])\n", "", [2], ["a"])
    assert r.finished == "exception" and r.exit_code == 1
    assert "IndexError" in r.stderr and "trace_harness" not in r.stderr
    assert len(r.hits) == 1


def test_timeout_returns_partial_hits():
    r = trace("i = 0\nwhile True:\n    i += 1\n", "", [3], ["i"], max_hits=4, time_limit_s=0.2)
    assert r.timed_out and len(r.hits) == 4 and r.hint
