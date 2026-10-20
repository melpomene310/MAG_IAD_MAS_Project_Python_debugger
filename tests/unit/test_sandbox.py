from pathlib import Path

from debugmas.data.schema import TestCase
from debugmas.sandbox.runner import RunResult, run_program, run_tests


def test_ac_and_stdin():
    r = run_program("print(sum(map(int, input().split())))", "2 3\n")
    assert r.stdout == "5\n" and r.exit_code == 0 and not r.timed_out


def test_infinite_loop_is_tle():
    r = run_program("while True:\n    pass\n", "", time_limit_s=0.3)
    assert r.timed_out
    assert r.wall_time < 5


def test_exception_is_re():
    r = run_program("raise ValueError('boom')", "")
    assert r.exit_code == 1 and "ValueError" in r.stderr


def test_memory_limit():
    r = run_program("a = [0] * (10**9)\n", "", memory_mb=256)
    assert r.memory_exceeded and r.exit_code != 0


def test_exit_codes():
    assert run_program("exit()", "").exit_code == 0
    assert run_program("import sys\nsys.exit(3)", "").exit_code == 3


def test_threads():
    code = (
        "import threading\n"
        "def f():\n    print(42)\n"
        "threading.stack_size(1 << 26)\n"
        "t = threading.Thread(target=f)\nt.start()\nt.join()\n"
    )
    assert run_program(code, "").stdout == "42\n"


def test_workdir_isolation():
    code = "import os\nprint(sorted(os.listdir('.')))\nprint(os.environ.get('OPENAI_API_KEY'))"
    r = run_program(code, "")
    assert r.stdout.splitlines() == ["['main.py']", "None"]


def test_isolated_mode_no_app_imports():
    r = run_program("import debugmas", "")
    assert r.exit_code != 0 and "ModuleNotFoundError" in r.stderr


def test_output_truncated_when_stored():
    r = run_program("print('x' * 200000)", "")
    assert len(r.stdout) == 200001
    stored = r.to_dict(max_bytes=1000)
    assert len(stored["stdout"]) < 1100 and "обрезано" in stored["stdout"]


def test_run_tests_parallel_with_float_tolerance(tmp_path: Path):
    tests = []
    for i, (inp, out) in enumerate(
        [("1 2\n", "1.5\n"), ("1 1\n", "1.0000001\n"), ("1 4\n", "3\n")]
    ):
        fi, fo = tmp_path / f"{i}.in", tmp_path / f"{i}.out"
        fi.write_text(inp)
        fo.write_text(out)
        tests.append(TestCase(str(i), fi, fo))
    res = run_tests("a, b = map(int, input().split())\nprint((a + b) / 2)", tests, workers=3)
    assert [r.verdict for r in res] == ["AC", "AC", "WA"]


def test_runresult_dict_keys():
    r = RunResult("a", "b", 0, False, False, 0.1).to_dict()
    assert set(r) == {"stdout", "stderr", "exit_code", "timed_out", "memory_exceeded", "wall_time"}
