"""Метрики сравнения (docs/spec.md, раздел 10.2; лекция 6 «Качество, стоимость, задержка и бюджет»).

Все метрики считаются по всем задачам выборки: `error` и исчерпанные лимиты — неудача,
их расходы и время входят в затраты.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any

from debugmas.eval.evaluate import FAILURE_REASONS, TaskEval
from debugmas.llm.usage import Usage

QUANTILE_RULE = "ближайший ранг: значение с номером ceil(q·n) в отсортированном ряду"


def share(k: int, n: int) -> dict[str, Any]:
    """Доля успехов = успешные эпизоды / все эпизоды протокола (слайд 16)."""
    return {"k": k, "n": n, "rate": k / n if n else None}


def nearest_rank(values: Sequence[float], q: float) -> float | None:
    """Квантиль по правилу ближайшего ранга (слайды 36–37)."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(q * len(ordered))) - 1]


def time_stats(values: Sequence[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "median": nearest_rank(values, 0.5),
        "p95": nearest_rank(values, 0.95),
        "max": max(values) if values else None,
        "total": float(sum(values)),
        "rule": QUANTILE_RULE,
    }


def cost_stats(usages: Sequence[Usage], costs: Sequence[float], successes: int) -> dict[str, Any]:
    """Полный расход (слайды 27–30): вход без кэша, кэшированный вход, выход.

    Стоимость успеха = все расходы / число успешных эпизодов; при нуле успехов не определена.
    Запросы без usage не заменяются нулём, а считаются отдельно.
    """
    total = sum(usages, Usage())
    cost_total = float(sum(costs))
    n = len(usages)
    return {
        "tokens": {
            "input_uncached": total.uncached_input,
            "input_cached": total.cached_input,
            "output": total.output,
            "reasoning": total.reasoning,  # входит в output
            "total": total.total,
        },
        "requests": {
            "ok": total.calls,
            "failed": total.failed_calls,
            "without_usage": total.calls_without_usage,
            "failed_without_usage": total.failed_without_usage,
        },
        "cost_total": cost_total,
        "cost_per_episode": cost_total / n if n else None,
        "successes": successes,
        "cost_per_success": cost_total / successes if successes else None,
    }


def group_metrics(evals: Sequence[TaskEval]) -> dict[str, Any]:
    n = len(evals)
    finals = sum(e.final_success for e in evals)
    reasons = Counter(e.failure_reason for e in evals if e.failure_reason)
    return {
        "n_tasks": n,
        "first_attempt_success": share(sum(e.first_attempt_success for e in evals), n),
        "final_success": share(finals, n),
        "partial": share(sum(e.partial for e in evals), n),
        "fault_line_hit": share(sum(e.fault_line_hit for e in evals), n),
        "suspicious_patch": share(sum(bool(e.suspicious) for e in evals), n),
        "status": dict(Counter(e.status for e in evals)),
        "failure_reasons": {r: reasons.get(r, 0) for r in FAILURE_REASONS},
        "costs": cost_stats([e.usage for e in evals], [e.cost for e in evals], finals),
        "time": time_stats([e.wall_time_s for e in evals]),
    }


def llm_only_metrics(evals: Sequence[TaskEval]) -> dict[str, Any]:
    """LLM-only = первая попытка `workflow`; расход и время — только первой попытки."""
    n = len(evals)
    firsts = sum(e.first_attempt_success for e in evals)
    return {
        "n_tasks": n,
        "first_attempt_success": share(firsts, n),
        "final_success": share(firsts, n),
        "costs": cost_stats([e.first_usage for e in evals], [e.first_cost for e in evals], firsts),
        "time": time_stats([e.first_wall_time_s for e in evals]),
    }


def _by_bin(
    evals: Sequence[TaskEval], bins: Sequence[str], fn: Callable[[Sequence[TaskEval]], Any]
) -> dict[str, Any]:
    return {b: fn([e for e in evals if e.bin == b]) for b in bins}


def compute_metrics(evals: Sequence[TaskEval], bin_order: Sequence[str] = ()) -> dict[str, Any]:
    bins = list(bin_order) or sorted({e.bin for e in evals if e.bin is not None})
    solver = evals[0].solver if evals else None
    out: dict[str, Any] = {
        "solver": solver,
        "overall": group_metrics(evals),
        "by_bin": _by_bin(evals, bins, group_metrics),
    }
    if solver == "workflow":
        out["llm_only"] = {
            "overall": llm_only_metrics(evals),
            "by_bin": _by_bin(evals, bins, llm_only_metrics),
        }
    return out


def pairwise(a: dict[str, bool], b: dict[str, bool]) -> dict[str, Any]:
    """Парное сравнение на общих задачах и счёт 2/1/0 (слайды 23–24).

    `a`, `b`: task_id -> решена ли задача. Победа — 2 балла, ничья — 1 каждому, поражение — 0.
    """
    common = sorted(set(a) & set(b))
    both = sum(a[t] and b[t] for t in common)
    only_a = sum(a[t] and not b[t] for t in common)
    only_b = sum(b[t] and not a[t] for t in common)
    neither = len(common) - both - only_a - only_b
    draws = both + neither
    score_a, score_b = 2 * only_a + draws, 2 * only_b + draws
    total = score_a + score_b
    return {
        "n": len(common),
        "both": both,
        "only_a": only_a,
        "only_b": only_b,
        "neither": neither,
        "score_a": score_a,
        "score_b": score_b,
        "score_share_a": score_a / total if total else None,
        "score_share_b": score_b / total if total else None,
    }


def repeat_metrics(runs: Sequence[dict[str, bool]]) -> dict[str, Any]:
    """Повторы одного варианта (слайд 18).

    Успех запуска — доля успешных эпизодов среди всех запусков; стабильность — доля задач,
    решённых во всех повторах; хотя бы один успех — доля задач, решённых хоть раз
    (это результат k попыток, а не одной).
    """
    common = sorted(set.intersection(*(set(r) for r in runs))) if runs else []
    episodes = [r[t] for r in runs for t in common]
    return {
        "repeats": len(runs),
        "n_tasks": len(common),
        "run_success": share(sum(episodes), len(episodes)),
        "stability": share(sum(all(r[t] for r in runs) for t in common), len(common)),
        "at_least_one": share(sum(any(r[t] for r in runs) for t in common), len(common)),
    }


def pareto_front(points: dict[str, tuple[float, float]]) -> list[str]:
    """Варианты без явного проигрыша по (цена ↓, успех ↑) (слайд 39)."""
    front = []
    for name, (cost, succ) in points.items():
        dominated = any(
            c <= cost and s >= succ and (c < cost or s > succ)
            for other, (c, s) in points.items()
            if other != name
        )
        if not dominated:
            front.append(name)
    return front
