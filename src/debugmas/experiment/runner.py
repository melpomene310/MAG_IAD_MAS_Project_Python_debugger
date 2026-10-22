"""Запуск эксперимента: решатель × выборка (docs/spec.md, разделы 5.3 и 10.1)."""

from __future__ import annotations

import json
import logging
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from debugmas.config import (
    CONFIGS_DIR,
    ExperimentConfig,
    Settings,
    load_yaml,
    resolve_llm,
    resolved_config_dict,
)
from debugmas.data.prepare import load_index
from debugmas.data.schema import load_agent_view
from debugmas.data.splits import bin_of, read_manifest
from debugmas.experiment.results import RunDir, build_meta, git_info
from debugmas.experiment.tracing import EventSink, TaskTracer
from debugmas.llm.cache import LLMCache
from debugmas.llm.client import ChatModel, LLMClient
from debugmas.llm.fake import fake_for, load_fake_scripts
from debugmas.llm.usage import Usage
from debugmas.solvers.base import RunContext, SolverLimits, SolverResult, make_solver
from debugmas.tools.registry import ToolRegistry

log = logging.getLogger(__name__)

PROTECTED_SPLIT = "test"


class RunError(RuntimeError):
    pass


def preset_bins(preset: str, splits_config: Path | None = None) -> dict[str, list[int | None]]:
    cfg = load_yaml(splits_config or CONFIGS_DIR / "splits.yaml")
    presets = cfg.get("presets", {})
    if preset not in presets:
        raise RunError(f"Нет пресета '{preset}' в configs/splits.yaml")
    return presets[preset]["bins"]


def select_tasks(
    cfg: ExperimentConfig,
    split: str,
    bins: dict[str, list[int | None]],
    task_filter: list[str] | None = None,
    limit: int | None = None,
) -> list[str]:
    data_dir = Path(cfg.data_dir)
    index = {row["task_id"]: row for row in load_index(data_dir)}
    if split == "all":
        ids = sorted(index)
    else:
        ids = read_manifest(Path(cfg.splits_dir), cfg.split_preset, split)
    if cfg.bins:
        ids = [
            t for t in ids if t in index and bin_of(index[t].get("difficulty"), bins) in cfg.bins
        ]
    if task_filter:
        ids = [t for t in ids if t in set(task_filter)]
    if limit:
        ids = ids[:limit]
    return ids


def make_llm_factory(
    cfg: ExperimentConfig, settings: Settings, llm: dict[str, Any]
) -> Callable[[str], ChatModel]:
    if cfg.llm.fake:
        if not cfg.llm.fake_script:
            raise RunError("llm.fake=true требует llm.fake_script")
        scripts = load_fake_scripts(cfg.llm.fake_script)
        return lambda task_id: fake_for(scripts, cfg.solver, task_id)
    cache = LLMCache(llm["cache_dir"]) if llm["cache_enabled"] else None

    def factory(task_id: str) -> ChatModel:
        return LLMClient(
            model=llm["model"],
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            temperature=llm["temperature"],
            timeout_s=llm["timeout_s"],
            max_retries=llm["max_retries"],
            max_output_tokens=llm["max_output_tokens"],
            reasoning=llm["reasoning"],
            cache=cache,
            repeat_idx=llm["repeat_idx"],
        )

    return factory


def _find_resumable(results_dir: Path, suffix: str) -> Path | None:
    if not results_dir.exists():
        return None
    cands = sorted(p for p in results_dir.iterdir() if p.is_dir() and p.name.endswith(suffix))
    return cands[-1] if cands else None


def solve_task(
    task_id: str,
    cfg: ExperimentConfig,
    llm_factory: Callable[[str], ChatModel],
    sink: EventSink,
    run_id: str,
) -> SolverResult:
    tracer = TaskTracer(sink, run_id, task_id, cfg.solver)
    try:
        view = load_agent_view(Path(cfg.data_dir) / "tasks" / task_id)
        solver = make_solver(cfg.solver, cfg)
        ctx = RunContext(
            llm=llm_factory(task_id),
            tools=ToolRegistry(cfg.tools),
            limits=SolverLimits(
                max_attempts=cfg.max_attempts,
                max_steps=cfg.max_steps,
                max_tokens_per_task=cfg.max_tokens_per_task,
                task_timeout_s=cfg.task_timeout_s,
            ),
            tracer=tracer,
            config=cfg,
        )
        tracer.emit("task_start")
        result = solver.solve(view, ctx)
    except Exception as exc:  # noqa: BLE001 — падение на задаче не останавливает запуск
        log.exception("Решатель упал на задаче %s", task_id)
        tracer.emit("crash", error=traceback.format_exc())
        result = SolverResult(
            task_id=task_id,
            solver=cfg.solver,
            status="error",
            attempts=[],
            final_code=None,
            usage=Usage(),
            wall_time_s=0.0,
            llm_time_s=0.0,
            sandbox_time_s=0.0,
            steps=0,
            tool_calls={},
            error=f"{type(exc).__name__}: {exc}",
        )
    tracer.emit(
        "task_end",
        result={"status": result.status, "attempts": len(result.attempts), "error": result.error},
        usage=result.usage.short(),
    )
    return result


def run_experiment(
    cfg: ExperimentConfig,
    split: str,
    *,
    settings: Settings | None = None,
    task_filter: list[str] | None = None,
    limit: int | None = None,
    resume: bool = True,
    out_dir: Path | None = None,
    final: bool = False,
    verbose: bool = False,
) -> Path:
    settings = settings or Settings()
    if split == PROTECTED_SPLIT and not final:
        raise RunError("Выборка test доступна только через `make final` (docs/spec.md, раздел 5.3)")
    if final and (task_filter or limit or verbose):
        raise RunError("final: фильтры по задачам (--task, --limit) и подробный вывод запрещены")

    bins = preset_bins(cfg.split_preset)
    task_ids = select_tasks(cfg, split, bins, task_filter, limit)
    llm = resolve_llm(cfg, settings)
    resolved = resolved_config_dict(cfg, settings)
    resolved["split"] = split
    resolved["preset_bins"] = bins
    resolved["task_filter"] = task_filter
    resolved["limit"] = limit

    results_dir = Path(cfg.results_dir)
    suffix = f"_{cfg.solver}_{split}_{cfg.short_hash(llm)}"
    if out_dir is None:
        existing = _find_resumable(results_dir, suffix) if resume else None
        date = datetime.now(UTC).strftime("%Y%m%d")
        out_dir = existing or results_dir / f"{date}{suffix}"
    run_dir = RunDir(out_dir)
    run_id = out_dir.name
    done = run_dir.done_task_ids() if resume else set()
    if not resume and run_dir.tasks_path.exists():
        run_dir.tasks_path.unlink()
        if run_dir.trace_path.exists():
            run_dir.trace_path.unlink()

    if task_filter and done:
        resolved["task_filter"] = sorted(done | set(task_ids))
    run_dir.write_config(resolved)
    meta = run_dir.read_meta() or build_meta(run_id, llm, {"split": split, "final": final})
    meta["n_tasks"] = len(done | set(task_ids))
    meta["finished"] = None
    meta.setdefault("resumed_at", [])
    if done:
        meta["resumed_at"].append(datetime.now(UTC).isoformat())
    run_dir.write_meta(meta)

    todo = [t for t in task_ids if t not in done]
    log.info("Запуск %s: задач %d, уже готово %d", run_id, len(task_ids), len(done))
    sink = EventSink(run_dir.trace_path)
    factory = make_llm_factory(cfg, settings, llm)
    workers = cfg.concurrency or settings.llm_max_concurrency
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(solve_task, t, cfg, factory, sink, run_id): t for t in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            run_dir.append_result(res)
            log.info("[%d/%d] %s: %s", i, len(todo), res.task_id, res.status)

    meta["finished"] = datetime.now(UTC).isoformat()
    run_dir.write_meta(meta)
    write_metrics(out_dir)
    return out_dir


def write_metrics(run_dir: Path) -> dict[str, Any]:
    from debugmas.eval.evaluate import evaluate_run
    from debugmas.eval.metrics import compute_metrics

    evals, cfg = evaluate_run(run_dir)
    metrics = compute_metrics(evals, list((cfg.get("preset_bins") or {}).keys()))
    metrics["tasks"] = [e.to_dict() for e in evals]
    (run_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return metrics


def run_final(cfg: ExperimentConfig, run_tag: str, settings: Settings | None = None) -> Path:
    """Прогон на закрытой выборке test (docs/spec.md, раздел 5.3)."""
    if not run_tag:
        raise RunError("Нужен RUN_TAG")
    git = git_info()
    if git["commit"] is None:
        raise RunError("final: нет git-коммита")
    if git["dirty"]:
        raise RunError("final: рабочее дерево git не чистое — закоммитьте изменения")
    out_dir = Path(cfg.results_dir) / "final" / run_tag
    if out_dir.exists():
        raise RunError(f"final: тег {run_tag} уже существует ({out_dir}), перезапись запрещена")
    cfg = cfg.model_copy(deep=True)
    cfg.llm.cache_enabled = False
    return run_experiment(
        cfg, PROTECTED_SPLIT, settings=settings, resume=False, out_dir=out_dir, final=True
    )
