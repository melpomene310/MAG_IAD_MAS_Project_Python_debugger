"""Исход одного эпизода (задачи) по результатам запуска.

Эпизод — от получения задачи до итогового результата; все попытки и неудачные запросы
входят в расход (лекция 6, слайд 14). Статус исполнения и качество хранятся отдельно (слайд 15).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from debugmas.data.ground_truth import load_ground_truth
from debugmas.data.prepare import load_index
from debugmas.data.schema import load_agent_view
from debugmas.data.splits import bin_of
from debugmas.eval.patch_analysis import diff_code, fault_line_hit, suspicious_reasons
from debugmas.llm.usage import Usage
from debugmas.solvers.base import SolverResult

# Причины провала (слайд 19). «Взаимодействие» появится у MAS.
FAILURE_REASONS = ("решение", "бюджет", "инфраструктура", "взаимодействие")


@dataclass
class TaskEval:
    task_id: str
    solver: str
    status: str
    bin: str | None
    first_attempt_success: bool
    final_success: bool
    tests_passed: int  # итоговая версия: частичный результат
    tests_total: int
    failure_reason: str | None
    fault_line_hit: bool  # метрика нашей задачи: правка в строке ошибки по разметке
    suspicious: list[str]  # признаки подгонки под тесты (для ручной проверки)
    usage: Usage
    first_usage: Usage  # LLM-only: только первая попытка
    cost: float
    first_cost: float
    wall_time_s: float
    first_wall_time_s: float
    error: str | None = None

    @property
    def partial(self) -> bool:
        return not self.final_success and self.tests_passed > 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["usage"] = self.usage.to_dict()
        d["first_usage"] = self.first_usage.to_dict()
        return d


def failure_reason(res: SolverResult) -> str | None:
    if res.status == "solved":
        return None
    if res.status == "attempts_exhausted":
        return "решение"
    if res.status in ("step_limit", "token_limit"):
        return "бюджет"
    if res.error and res.error.startswith("task_timeout"):
        return "бюджет"
    return "инфраструктура"  # недоступная модель, таймауты API, падение решателя


def load_results(run_dir: Path) -> list[SolverResult]:
    path = run_dir / "tasks.jsonl"
    if not path.exists():
        return []
    out: dict[str, SolverResult] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = SolverResult.from_dict(json.loads(line))
                out[r.task_id] = r  # при повторе берётся последняя запись
    return list(out.values())


def load_run_config(run_dir: Path) -> dict[str, Any]:
    with open(run_dir / "config.resolved.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def prices(cfg: dict[str, Any]) -> tuple[float, float, float]:
    llm = cfg.get("llm_resolved", {})
    pin = float(llm.get("price_input_per_1m") or 0)
    pcached = llm.get("price_cached_input_per_1m")
    return (
        pin,
        float(pin if pcached is None else pcached),
        float(llm.get("price_output_per_1m") or 0),
    )


MAX_TESTS_FOR_PATCH_ANALYSIS = 200


def _patch_checks(res: SolverResult, task_dir: Path) -> tuple[bool, list[str]]:
    if not res.final_code or not (task_dir / "agent_view.json").exists():
        return False, []
    view = load_agent_view(task_dir)
    gt = load_ground_truth(task_dir)
    hit = fault_line_hit(diff_code(view.code, res.final_code), gt.fault_lines)
    tests = view.tests[:MAX_TESTS_FOR_PATCH_ANALYSIS]
    reasons = suspicious_reasons(
        view.code,
        res.final_code,
        [t.read_expected() for t in tests],
        [t.read_input() for t in tests],
    )
    return hit, reasons


def evaluate_result(
    res: SolverResult,
    index_row: dict[str, Any] | None,
    bins: dict[str, list[int | None]],
    price: tuple[float, float, float],
    task_dir: Path,
) -> TaskEval:
    first = res.attempts[0] if res.attempts else None
    final_success = any(a.passed_all for a in res.attempts)
    graded = [a for a in res.attempts if a.verdicts]
    last = next((a for a in res.attempts if a.passed_all), graded[-1] if graded else None)
    n_tests = int((index_row or {}).get("n_tests") or 0)
    tests_total = len(last.verdicts) if last else n_tests
    tests_passed = sum(v == "AC" for v in last.verdicts.values()) if last else 0
    # workflow: usage попытки — токены этой попытки; single_agent — накопленные до неё
    first_usage = first.usage if first else res.usage
    hit, suspicious = _patch_checks(res, task_dir)
    return TaskEval(
        task_id=res.task_id,
        solver=res.solver,
        status=res.status,
        bin=bin_of((index_row or {}).get("difficulty"), bins),
        first_attempt_success=bool(first and first.passed_all),
        final_success=final_success,
        tests_passed=tests_passed,
        tests_total=tests_total,
        failure_reason=failure_reason(res),
        fault_line_hit=hit,
        suspicious=suspicious,
        usage=res.usage,
        first_usage=first_usage,
        cost=res.usage.cost(*price),
        first_cost=first_usage.cost(*price),
        wall_time_s=res.wall_time_s,
        first_wall_time_s=first.wall_time_s if first else res.wall_time_s,
        error=res.error,
    )


def evaluate_run(run_dir: Path) -> tuple[list[TaskEval], dict[str, Any]]:
    cfg = load_run_config(run_dir)
    data_dir = Path(cfg["data_dir"])
    has_index = (data_dir / "index.jsonl").exists()
    index = {r["task_id"]: r for r in load_index(data_dir)} if has_index else {}
    bins = cfg.get("preset_bins") or {}
    price = prices(cfg)
    evals = [
        evaluate_result(r, index.get(r.task_id), bins, price, data_dir / "tasks" / r.task_id)
        for r in load_results(run_dir)
    ]
    evals.sort(key=lambda e: e.task_id)
    return evals, cfg
