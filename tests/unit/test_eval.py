import pytest

from debugmas.eval.evaluate import TaskEval
from debugmas.eval.metrics import (
    compute_metrics,
    nearest_rank,
    pairwise,
    pareto_front,
    repeat_metrics,
    time_stats,
)
from debugmas.eval.patch_analysis import diff_code, fault_line_hit, suspicious_reasons
from debugmas.llm.usage import Usage


def ev(
    task,
    solver="workflow",
    first=False,
    final=False,
    status="solved",
    tokens=100,
    bin_="easy",
    first_tokens=None,
    cost=None,
    time=1.0,
    passed=0,
    reason=None,
    hit=False,
) -> TaskEval:
    u = Usage(input=tokens, output=0, calls=1)
    fu = Usage(input=first_tokens if first_tokens is not None else tokens, calls=1)
    return TaskEval(
        task_id=task,
        solver=solver,
        status=status,
        bin=bin_,
        first_attempt_success=first,
        final_success=final,
        tests_passed=passed,
        tests_total=10,
        failure_reason=reason,
        fault_line_hit=hit,
        suspicious=[],
        usage=u,
        first_usage=fu,
        cost=cost if cost is not None else tokens / 100,
        first_cost=fu.input / 100,
        wall_time_s=time,
        first_wall_time_s=time / 2,
    )


def test_first_and_final_success_over_all_tasks():
    # слайд 17: 24 с первой попытки, 6 после исправлений, 10 не решены
    evals = (
        [ev(f"a{i}", first=True, final=True) for i in range(24)]
        + [ev(f"b{i}", final=True) for i in range(6)]
        + [ev(f"c{i}", status="attempts_exhausted", reason="решение") for i in range(10)]
    )
    o = compute_metrics(evals)["overall"]
    assert o["first_attempt_success"] == {"k": 24, "n": 40, "rate": 0.6}
    assert o["final_success"]["rate"] == 0.75


def test_cost_per_success_includes_failures():
    # слайд 29: 20 эпизодов на 12 у.е., 15 успешных → 0.6 за эпизод, 0.8 за успех
    evals = [ev(f"s{i}", final=True, cost=0.6) for i in range(15)] + [
        ev(f"f{i}", status="error", cost=0.6, reason="инфраструктура") for i in range(5)
    ]
    c = compute_metrics(evals)["overall"]["costs"]
    assert c["cost_total"] == pytest.approx(12)
    assert c["cost_per_episode"] == pytest.approx(0.6)
    assert c["cost_per_success"] == pytest.approx(0.8)


def test_cost_per_success_undefined_without_successes():
    c = compute_metrics([ev("a", status="error", reason="инфраструктура")])["overall"]["costs"]
    assert c["cost_per_success"] is None and c["cost_total"] > 0


def test_usage_cost_with_cache():
    # слайд 28: 8000 без кэша по 2, 12000 из кэша по 0.5, 2000 выхода по 8 → 0.038
    u = Usage(input=20_000, cached_input=12_000, output=2_000)
    assert u.cost(2, 0.5, 8) == pytest.approx(0.016 + 0.006 + 0.016)


def test_nearest_rank_quantiles():
    # слайд 36: 60×5 с, 30×8 с, 5×12 с, 5×40 с → медиана 5, p95 12, максимум 40
    values = [5] * 60 + [8] * 30 + [12] * 5 + [40] * 5
    t = time_stats(values)
    assert (t["median"], t["p95"], t["max"], t["n"]) == (5, 12, 40, 100)
    # слайд 37: на 12 наблюдениях p95 совпадает с максимумом
    assert nearest_rank(list(range(1, 13)), 0.95) == 12


def test_pairwise_score():
    # слайды 23–24: 60 оба, 10 только агент, 20 только MAS, 10 никто → 110 : 90
    a, b = {}, {}
    for i in range(100):
        a[i], b[i] = (i < 60 or 60 <= i < 70), (i < 60 or 70 <= i < 90)
    p = pairwise(b, a)  # MAS vs агент
    assert (p["both"], p["only_a"], p["only_b"], p["neither"]) == (60, 20, 10, 10)
    assert (p["score_a"], p["score_b"]) == (110, 90)
    assert p["score_share_a"] == pytest.approx(0.55)


def test_repeats():
    # слайд 18: A ✓✓✓, B ✓✗✓, C ✗✓✗, D ✗✗✗
    runs = [
        {"A": True, "B": True, "C": False, "D": False},
        {"A": True, "B": False, "C": True, "D": False},
        {"A": True, "B": True, "C": False, "D": False},
    ]
    m = repeat_metrics(runs)
    assert m["run_success"]["rate"] == 0.5
    assert m["stability"]["rate"] == 0.25
    assert m["at_least_one"]["rate"] == 0.75


def test_pareto_front():
    # слайд 39: A(1,70) B(2,80) C(3,75) D(4,84) → фронт A, B, D
    pts = {"A": (1, 0.70), "B": (2, 0.80), "C": (3, 0.75), "D": (4, 0.84)}
    assert pareto_front(pts) == ["A", "B", "D"]


def test_failure_reasons_partial_and_llm_only():
    evals = [
        ev("a", first=True, final=True, hit=True),
        ev("b", status="attempts_exhausted", reason="решение", passed=7),
        ev("c", status="token_limit", reason="бюджет"),
        ev("d", status="error", reason="инфраструктура", first_tokens=10),
    ]
    m = compute_metrics(evals)
    o = m["overall"]
    assert o["failure_reasons"] == {
        "решение": 1,
        "бюджет": 1,
        "инфраструктура": 1,
        "взаимодействие": 0,
    }
    assert o["partial"]["k"] == 1 and o["fault_line_hit"]["k"] == 1
    assert m["llm_only"]["overall"]["costs"]["tokens"]["total"] == 100 + 100 + 100 + 10
    assert "llm_only" not in compute_metrics([ev("a", solver="single_agent")])


def test_unknown_usage_not_replaced_by_zero():
    u = Usage(calls=1, calls_without_usage=1) + Usage(failed_calls=1, failed_without_usage=1)
    e = ev("a")
    e.usage = u
    c = compute_metrics([e])["overall"]["costs"]
    assert c["requests"]["without_usage"] == 1 and c["requests"]["failed_without_usage"] == 1
    assert c["tokens"]["total"] == 0


ORIG = "n = int(input())\nfor i in range(1, n):\n    pass\nprint(n)\n"


def test_fault_line_hit():
    d = diff_code(ORIG, ORIG.replace("range(1, n)", "range(1, n + 1)"))
    assert d.changed_lines == {2}
    assert fault_line_hit(d, [2]) and not fault_line_hit(d, [4])
    assert diff_code(ORIG, ORIG.replace("\n", "  \n")).changed_lines == set()


def test_suspicious_patches():
    outs, ins = ["12586269025\n", "1\n"], ["50\n", "1\n"]
    hard = ORIG.replace("print(n)", "print(12586269025 if n == 50 else n)")
    reasons = suspicious_reasons(ORIG, hard, outs, ins)
    assert any(r.startswith("literal_matches_expected_output") for r in reasons)
    assert any(r.startswith("compares_with_test_input") for r in reasons)
    fs = ORIG.replace("print(n)", "import os\nprint(os.listdir('.'))")
    assert any(r.startswith("forbidden_access") for r in suspicious_reasons(ORIG, fs, outs, ins))
    big = ORIG + "".join(f"x{i} = {i}\n" for i in range(20))
    assert any(r.startswith("large_patch") for r in suspicious_reasons(ORIG, big, outs, ins))
    assert suspicious_reasons(ORIG, ORIG.replace("range(1, n)", "range(1, n + 1)"), outs, ins) == []
