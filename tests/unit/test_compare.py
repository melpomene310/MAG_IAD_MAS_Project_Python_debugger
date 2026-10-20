from debugmas.sandbox.compare import judge, outputs_match, tokens_equal
from debugmas.sandbox.runner import RunResult


def _res(stdout: str = "", code: int = 0, timed_out: bool = False, mem: bool = False) -> RunResult:
    return RunResult(stdout, "", code, timed_out, mem, 0.01)


def test_whitespace_tokens():
    assert outputs_match("1 2\n3\n", "1\n2 3")
    assert not outputs_match("1 2", "1 2 3")


def test_float_tolerance():
    assert tokens_equal("1.5000000001", "1.5")
    assert tokens_equal("1", "1.0000000")  # один из токенов с точкой
    assert tokens_equal("1e6", "1000000.0000001")
    assert not tokens_equal("1.51", "1.5")
    assert tokens_equal("123456789.0", "123456789.1")  # относительный допуск


def test_integers_compared_exactly():
    assert not tokens_equal("100", "101")
    assert not tokens_equal("1000000000000000001", "1000000000000000000")


def test_verdicts():
    assert judge(_res("3"), "3") == "AC"
    assert judge(_res("4"), "3") == "WA"
    assert judge(_res("3", code=1), "3") == "RE"
    assert judge(_res(timed_out=True), "3") == "TLE"
    assert judge(_res(code=1, mem=True), "3") == "MLE"
