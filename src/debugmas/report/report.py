"""`make report`: report.md и графики (docs/spec.md, раздел 10.3; лекция 6)."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

from debugmas.eval.evaluate import FAILURE_REASONS, TaskEval, evaluate_run
from debugmas.eval.metrics import compute_metrics, pairwise, pareto_front, repeat_metrics
from debugmas.report.charts import make_charts

log = logging.getLogger(__name__)

AGENT_SOLVERS = ("single_agent", "mas", "mas_sequential", "mas_competitive")
PILOT_SOLVERS = {"workflow", "single_agent", "mas_sequential"}
FIRST_ATTEMPT_RULE = (
    "Первая попытка — первая сданная программа до исправлений по результатам её проверки: "
    "у `workflow` — первый ответ модели, у `single_agent` — первый `submit`, "
    "у `mas_sequential` — первый ответ исправителя."
)


@dataclass
class RunData:
    path: Path
    label: str
    solver: str
    cfg: dict[str, Any]
    meta: dict[str, Any]
    evals: list[TaskEval]
    metrics: dict[str, Any]

    @property
    def by_task(self) -> dict[str, TaskEval]:
        return {e.task_id: e for e in self.evals}


@dataclass
class Variant:
    name: str
    block: dict[str, Any]  # {"overall": ..., "by_bin": ...}
    solved: dict[str, bool] = field(default_factory=dict)  # task_id -> итоговый успех


def load_run(path: Path) -> RunData:
    evals, cfg = evaluate_run(path)
    bins = list((cfg.get("preset_bins") or {}).keys())
    meta_path = path / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    solver = cfg.get("solver", "?")
    return RunData(path, solver, solver, cfg, meta, evals, compute_metrics(evals, bins))


def validate_pilot_comparison(runs: Sequence[RunData]) -> None:
    """Не строить пилотный отчёт, если три архитектуры запущены в разных условиях."""
    if not PILOT_SOLVERS <= {run.solver for run in runs}:
        return
    first = runs[0]
    if not first.evals:
        raise ValueError("Пилотное сравнение: в запусках нет задач")
    checks = {
        "набор задач": lambda r: sorted(e.task_id for e in r.evals),
        "каталог данных": lambda r: str(Path(r.cfg.get("data_dir", "")).resolve()),
        "выборка": lambda r: (r.cfg.get("split"), r.cfg.get("split_preset")),
        "модель и параметры вызовов": lambda r: [
            r.cfg.get("llm_resolved", {}).get(key)
            for key in (
                "model",
                "base_url",
                "temperature",
                "max_output_tokens",
                "reasoning",
                "fake",
                "timeout_s",
                "max_retries",
                "cache_enabled",
            )
        ],
        "тарифы": lambda r: [
            r.cfg.get("llm_resolved", {}).get(key)
            for key in ("price_input_per_1m", "price_cached_input_per_1m", "price_output_per_1m")
        ],
        "границы сложности": lambda r: r.cfg.get("preset_bins"),
        "лимиты и стартовая информация": lambda r: [
            r.cfg.get(key)
            for key in (
                "max_attempts",
                "max_steps",
                "max_tokens_per_task",
                "task_timeout_s",
                "initial_failing_shown",
                "show_expected_output",
            )
        ],
    }
    diffs = [name for name, get in checks.items() if any(get(r) != get(first) for r in runs[1:])]
    if diffs:
        raise ValueError(f"Пилотное сравнение: различаются {', '.join(diffs)}")


# ---------- форматирование ----------


def _share(d: dict[str, Any] | None) -> str:
    if not d or not d.get("n"):
        return "—"
    return f"{d['k']}/{d['n']} ({100 * d['rate']:.0f}%)"


def _money(x: float | None) -> str:
    return "не определена" if x is None else f"${x:.4f}"


def _num(x: float | None, digits: int = 1) -> str:
    if x is None:
        return "—"
    if abs(x) >= 1000:
        return f"{x:,.0f}".replace(",", " ")
    return f"{x:.{digits}f}"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return [*out, ""]


def _bin_order(runs: Sequence[RunData]) -> list[str]:
    order: list[str] = []
    for r in runs:
        for b in (r.cfg.get("preset_bins") or {}).keys():
            if b not in order:
                order.append(b)
    return order


def _variants(runs: Sequence[RunData]) -> list[Variant]:
    """LLM-only (первая попытка workflow) идёт первым, затем решатели."""
    out: list[Variant] = []
    for r in runs:
        if "llm_only" in r.metrics:
            name = "LLM-only" + r.label.removeprefix("workflow")
            solved = {e.task_id: e.first_attempt_success for e in r.evals}
            out.append(Variant(name, r.metrics["llm_only"], solved))
    for r in runs:
        out.append(Variant(r.label, r.metrics, {e.task_id: e.final_success for e in r.evals}))
    return out


# ---------- разделы ----------


def section_conditions(runs: Sequence[RunData], bins: list[str]) -> list[str]:
    lines = ["## 1. Условия сравнения", ""]
    first = runs[0]
    c, llm = first.cfg, first.cfg.get("llm_resolved", {})
    task_ids = sorted({e.task_id for r in runs for e in r.evals})
    per_bin = ", ".join(f"{b} {sum(e.bin == b for e in first.evals)}" for b in bins)
    git = first.meta.get("git", {})
    commit = git.get("commit")
    commit = f"`{commit[:10]}`" + (" (dirty)" if git.get("dirty") else "") if commit else "нет"
    fake = " — **фейковая LLM**" if llm.get("fake") else ""
    lines += [
        "**Критерий успеха:** исправленная программа проходит все тесты задачи. "
        "В знаменателе все задачи набора; `error` и остановка по лимиту — неудача, "
        "их расход учитывается.",
        "",
        FIRST_ATTEMPT_RULE,
        "",
        f"- Задачи: `{c.get('split')}` (пресет `{c.get('split_preset')}`), "
        f"{len(task_ids)} шт.: {per_bin or '—'}",
        f"- Модель: `{llm.get('model')}`{fake}, "
        f"endpoint `{first.meta.get('endpoint_host') or '—'}`",
        f"- Параметры вызовов: температура {llm.get('temperature')}, "
        f"max_output_tokens {llm.get('max_output_tokens')}, reasoning {llm.get('reasoning')}",
        f"- Лимиты на задачу: попыток {c.get('max_attempts')}, "
        f"токенов {c.get('max_tokens_per_task')}, таймаут {c.get('task_timeout_s')} с",
    ]
    for r in runs:
        if r.solver != "workflow":
            lines.append(
                f"- {r.label}: шагов не более {r.cfg.get('max_steps')}, "
                f"инструменты {', '.join(r.cfg.get('tools', []))}"
            )
    lines.append("- Фактический расход (максимум токенов на задачу / лимит):")
    for r in runs:
        peak = max((e.usage.total for e in r.evals), default=0)
        lines.append(f"  - {r.label}: {_num(peak, 0)} / {r.cfg.get('max_tokens_per_task')}")
    lines.append(f"- Коммит: {commit}")
    lines.append("- Запуски: " + ", ".join(f"{r.label} — `{r.path}`" for r in runs))
    lines += [
        "",
        "<details><summary>Идентификаторы задач</summary>",
        "",
        ", ".join(f"`{t}`" for t in task_ids),
        "",
        "</details>",
        "",
    ]

    checks = {
        "модель": lambda r: r.cfg.get("llm_resolved", {}).get("model"),
        "endpoint": lambda r: r.cfg.get("llm_resolved", {}).get("base_url"),
        "параметры вызовов": lambda r: [
            r.cfg.get("llm_resolved", {}).get(k)
            for k in ("temperature", "max_output_tokens", "reasoning")
        ],
        "max_attempts": lambda r: r.cfg.get("max_attempts"),
        "max_tokens_per_task": lambda r: r.cfg.get("max_tokens_per_task"),
        "стартовая информация": lambda r: [
            r.cfg.get("initial_failing_shown"),
            r.cfg.get("show_expected_output"),
        ],
        "набор задач": lambda r: sorted(e.task_id for e in r.evals),
    }
    diffs = [name for name, f in checks.items() if len({json.dumps(f(r)) for r in runs}) > 1]
    if diffs:
        lines += [
            f"> ⚠️ Условия запусков различаются: {', '.join(diffs)}. "
            "Сравниваются целые конфигурации, а не архитектуры.",
            "",
        ]
    return lines


def section_quality(runs: Sequence[RunData], variants: list[Variant], bins: list[str]) -> list[str]:
    lines = ["## 2. Качество", ""]
    rows = []
    for v in variants:
        o = v.block["overall"]
        rows.append(
            [v.name]
            + [_share(v.block["by_bin"].get(b, {}).get("final_success")) for b in bins]
            + [
                f"**{_share(o.get('final_success'))}**",
                _share(o.get("first_attempt_success")),
                _share(o.get("partial")) if "partial" in o else "—",
                _share(o.get("fault_line_hit")) if "fault_line_hit" in o else "—",
            ]
        )
    lines += _table(
        [
            "Вариант",
            *bins,
            "Итоговый успех",
            "С 1-й попытки",
            "Частично (часть тестов)",
            "Правка в строке ошибки",
        ],
        rows,
    )
    lines += [
        "LLM-only — первая попытка `workflow`: один вызов модели без обратной связи. "
        "«Правка в строке ошибки» — метрика нашей задачи: итоговый патч меняет строку, "
        "где по разметке ConDefects была ошибка.",
        "",
    ]

    rows = []
    for a, b in combinations(variants, 2):
        p = pairwise(a.solved, b.solved)
        if not p["n"]:
            continue
        shares = (
            f"{100 * p['score_share_a']:.0f}% : {100 * p['score_share_b']:.0f}%"
            if p["score_share_a"] is not None
            else "—"
        )
        rows.append(
            [
                f"{a.name} vs {b.name}",
                str(p["n"]),
                str(p["both"]),
                str(p["only_a"]),
                str(p["only_b"]),
                str(p["neither"]),
                f"{p['score_a']} : {p['score_b']}",
                shares,
            ]
        )
    if rows:
        lines += [
            "### Парное сравнение на одних задачах",
            "",
            "Победа — 2 балла, ничья (обе решили или обе не решили) — 1 каждому, поражение — 0.",
            "",
        ]
        lines += _table(
            [
                "Пара (A vs B)",
                "Задач",
                "Обе решили",
                "Только A",
                "Только B",
                "Никто",
                "Счёт A : B",
                "Доли баллов",
            ],
            rows,
        )

    by_solver: dict[str, list[RunData]] = {}
    for r in runs:
        by_solver.setdefault(r.solver, []).append(r)
    reps = {s: rs for s, rs in by_solver.items() if len(rs) > 1}
    if reps:
        lines += [
            "### Повторы",
            "",
            "Успех запуска — доля успешных эпизодов по всем повторам; стабильность — задача "
            "решена во всех повторах; хотя бы один успех — результат k попыток, а не одной.",
            "",
        ]
        rows = []
        for s, rs in reps.items():
            m = repeat_metrics([{e.task_id: e.final_success for e in r.evals} for r in rs])
            rows.append(
                [
                    s,
                    str(m["repeats"]),
                    _share(m["run_success"]),
                    _share(m["stability"]),
                    _share(m["at_least_one"]),
                ]
            )
        lines += _table(
            ["Вариант", "Повторов", "Успех запуска", "Стабильность", "Хотя бы один успех"], rows
        )
    return lines


def section_costs(variants: list[Variant], charts: list[dict[str, Any]]) -> list[str]:
    lines = ["## 3. Затраты и время", ""]
    rows = []
    for v in variants:
        o = v.block["overall"]
        c, t = o["costs"], o["time"]
        tok, req = c["tokens"], c["requests"]
        unknown = req["without_usage"] + req["failed_without_usage"]
        rows.append(
            [
                v.name,
                _share(o.get("final_success")),
                _num(tok["input_uncached"], 0),
                _num(tok["input_cached"], 0),
                f"{_num(tok['output'], 0)} ({_num(tok['reasoning'], 0)})",
                _money(c["cost_total"]),
                _money(c["cost_per_episode"]),
                _money(c["cost_per_success"]),
                str(req["failed"]),
                str(unknown),
                f"{_num(t['median'])} / {_num(t['p95'])} / {_num(t['max'])}",
            ]
        )
    lines += _table(
        [
            "Вариант",
            "Успех",
            "Вход без кэша",
            "Вход из кэша",
            "Выход (рассуждения)",
            "Стоимость всего",
            "Цена эпизода",
            "Стоимость успеха",
            "Неудачных запросов",
            "Запросов без usage",
            "Время эпизода: медиана / p95 / макс, с",
        ],
        rows,
    )
    n_obs = variants[0].block["overall"]["time"]["n"] if variants else 0
    lines += [
        "- Стоимость успеха = все расходы (включая неудачные эпизоды) / число успешных "
        "эпизодов; при нуле успехов не определена.",
        "- Запросы без usage не заменяются нулём: их расход неизвестен и в суммы не входит.",
        f"- Квантили по правилу ближайшего ранга, наблюдений: {n_obs}. "
        "На малом наборе p95 совпадает с максимумом.",
        "- Инструменты (запуск тестов, трассировка) выполняются локально и не оплачиваются.",
        "- Время LLM учитывается только для запросов не из кэша; для честного замера времени "
        "запускайте с выключенным кэшем.",
        "",
    ]
    points = {
        v.name: (
            v.block["overall"]["costs"]["cost_per_episode"] or 0.0,
            v.block["overall"]["final_success"]["rate"] or 0.0,
        )
        for v in variants
    }
    if len(points) > 1:
        front = pareto_front(points)
        lines += [
            f"**Парето-фронт (цена эпизода ↓, успех ↑):** {', '.join(front)}. "
            "Фронт относится только к показанным вариантам и этим двум метрикам.",
            "",
        ]
    lines += _chart_lines([c for c in charts if c["kind"] == "pareto"])
    return lines


def section_cases(runs: Sequence[RunData], variants: list[Variant]) -> list[str]:
    lines = ["## 4. Успехи и провалы", "", "### Причины провала", ""]
    rows = []
    for r in runs:
        fr = r.metrics["overall"]["failure_reasons"]
        rows.append([r.label, *(str(fr.get(x, 0)) for x in FAILURE_REASONS)])
    lines += _table(["Вариант", *FAILURE_REASONS], rows)
    lines += [
        "Решение — все попытки отклонены тестами; бюджет — остановка по лимиту шагов, "
        "токенов или времени; инфраструктура — сбой API или запуска; взаимодействие — сбой "
        "обмена между агентами (MAS).",
        "",
        "Хронология любой задачи: `make case RUN=results/<id> TASK=<task_id>`.",
        "",
    ]

    wf = next((r for r in runs if r.solver == "workflow"), None)
    for ag in (r for r in runs if r.solver in AGENT_SOLVERS):
        if wf is None:
            break
        common = sorted(set(ag.by_task) & set(wf.by_task))
        a_only = [
            t for t in common if ag.by_task[t].final_success and not wf.by_task[t].final_success
        ]
        w_only = [
            t for t in common if wf.by_task[t].final_success and not ag.by_task[t].final_success
        ]
        lines += [f"### {ag.label} решил, а workflow нет ({len(a_only)})", ""]
        lines += _task_list([f"`{t}`" for t in a_only])
        lines += [f"### workflow решил, а {ag.label} нет ({len(w_only)})", ""]
        lines += _task_list([f"`{t}`" for t in w_only])

    all_ids = set.intersection(*(set(v.solved) for v in variants)) if variants else set()
    failed_all = sorted(t for t in all_ids if not any(v.solved[t] for v in variants))
    lines += [f"### Все варианты провалились ({len(failed_all)})", ""]
    lines += _task_list([f"`{t}`" for t in failed_all])

    lines += ["### Остановки по лимиту и сбои", ""]
    lim = [
        f"`{e.task_id}` ({r.label}): {e.status}" + (f" — {e.error[:120]}" if e.error else "")
        for r in runs
        for e in r.evals
        if e.failure_reason in ("бюджет", "инфраструктура")
    ]
    lines += _task_list(lim, 50)
    return lines


def _task_list(items: list[str], limit: int = 30) -> list[str]:
    if not items:
        return ["- нет", ""]
    out = [f"- {t}" for t in items[:limit]]
    if len(items) > limit:
        out.append(f"- … и ещё {len(items) - limit}")
    return [*out, ""]


def _chart_lines(charts: Sequence[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for c in charts:
        if c["png"]:
            out.append(f"![{c['title']}]({c['png']})")
        out.append(f"[Интерактивная версия]({c['html']})")
        out.append("")
    return out


def build_report(run_dirs: Sequence[Path], out_root: Path = Path("results/reports")) -> Path:
    if not run_dirs:
        raise ValueError('Не указаны запуски: make report RUNS="results/<id1> results/<id2>"')
    runs = [load_run(Path(p)) for p in run_dirs]
    validate_pilot_comparison(runs)
    counts: dict[str, int] = {}
    for r in runs:
        counts[r.solver] = counts.get(r.solver, 0) + 1
    seen: dict[str, int] = {}
    for r in runs:
        if counts[r.solver] > 1:
            seen[r.solver] = seen.get(r.solver, 0) + 1
            r.label = f"{r.solver} (повтор {seen[r.solver]})"
    bins = _bin_order(runs)
    variants = _variants(runs)
    out_dir = out_root / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    charts = make_charts(variants, bins, out_dir)
    lines = [
        "# Отчёт: отладка Python-программ (ConDefects)",
        "",
        f"Сформирован: {datetime.now(UTC).isoformat(timespec='seconds')}.",
        "",
    ]
    lines += section_conditions(runs, bins)
    lines += section_quality(runs, variants, bins)
    lines += _chart_lines([c for c in charts if c["kind"] == "success"])
    lines += section_costs(variants, charts)
    lines += section_cases(runs, variants)
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    summary = {r.path.name: r.metrics for r in runs}
    (out_dir / "metrics_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )
    return out_dir / "report.md"
