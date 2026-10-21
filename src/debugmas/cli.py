"""CLI: `python -m debugmas <команда>` (docs/spec.md, раздел 3.3)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from debugmas.config import (
    CONFIGS_DIR,
    REPO_ROOT,
    load_experiment_config,
    load_yaml,
    parse_overrides,
)

FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures" / "condefects_mini"
SMOKE_DATA_DIR = Path("data/smoke/processed")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def cmd_data(args: argparse.Namespace) -> int:
    from debugmas.data.prepare import DataConfig, DataError, run_data

    raw = load_yaml(args.config)
    if args.limit:
        raw["limit_tasks"] = args.limit
    if args.task:
        raw["task_ids"] = args.task
    if args.out:
        raw["processed_dir"] = args.out
    try:
        report = run_data(DataConfig.from_dict(raw))
    except DataError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 2
    _print_validation(report)
    return 0


def _print_validation(report: dict) -> None:
    print(
        f"Задач всего: {report['n_tasks_total']}, оставлено: {report['n_tasks_kept']}, "
        f"отброшено: {report['n_tasks_dropped']}"
    )
    print("Отброшенные задачи по причинам:")
    for reason, n in report["dropped_tasks_by_reason"].items():
        print(f"  {reason}: {n}")
    print("Программы по причинам:")
    for reason, n in report["programs_by_reason"].items():
        print(f"  {reason}: {n}")
    if report["missing_libraries"]:
        print("Недостающие библиотеки (дополнить requirements-atcoder.txt):")
        for lib, n in report["missing_libraries"].items():
            print(f"  {lib}: {n}")


def cmd_split(args: argparse.Namespace) -> int:
    from debugmas.data.prepare import load_index
    from debugmas.data.splits import make_splits, write_manifests

    cfg = load_yaml(args.splits_config)
    index = load_index(Path(args.data_dir))
    presets = list(cfg["presets"]) if args.all else [args.preset]
    for preset in presets:
        splits = make_splits(
            index,
            cfg["presets"][preset]["bins"],
            cfg["sizes"],
            int(cfg["seed"]),
            preset,
            reserved_dev=set(cfg.get("reserved_dev", [])),
        )
        write_manifests(splits, Path(args.out) / preset)
        sizes = ", ".join(f"{k}={len(v)}" for k, v in splits.items())
        print(f"{preset}: {sizes} → {Path(args.out) / preset}")
    return 0


def _experiment_config(args: argparse.Namespace):  # noqa: ANN202
    overrides = parse_overrides(args.set)
    if getattr(args, "solver", None):
        overrides["solver"] = args.solver
    return load_experiment_config(args.config, overrides)


def cmd_run(args: argparse.Namespace) -> int:
    from debugmas.experiment.runner import RunError, run_experiment

    cfg = _experiment_config(args)
    try:
        out = run_experiment(
            cfg,
            args.split,
            task_filter=args.task or None,
            limit=args.limit,
            resume=args.resume,
            verbose=args.verbose,
        )
    except RunError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 2
    _print_run(out)
    return 0


def _print_run(out: Path) -> None:
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    o = metrics["overall"]
    print(f"Результаты: {out}")
    print(
        f"first_attempt_success={o['first_attempt_success']['k']}/{o['n_tasks']}, "
        f"final_success={o['final_success']['k']}/{o['n_tasks']}, статусы={o['status']}"
    )


def cmd_final(args: argparse.Namespace) -> int:
    from debugmas.experiment.runner import RunError, run_final

    if args.verbose:
        print("ОШИБКА: final запрещает подробный вывод (-v)", file=sys.stderr)
        return 2
    cfg = _experiment_config(args)
    try:
        out = run_final(cfg, args.run_tag)
    except RunError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 2
    _print_run(out)
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    from debugmas.data.condefects import TestSource
    from debugmas.data.prepare import prepare_dataset
    from debugmas.experiment.runner import run_experiment
    from debugmas.report.report import build_report

    cfg = load_experiment_config(args.config, {"solver": args.solver, **parse_overrides(args.set)})
    data_dir = Path(cfg.data_dir)
    report = prepare_dataset(
        FIXTURES_ROOT,
        TestSource(test_dir=FIXTURES_ROOT / "Test"),
        data_dir,
        seed=42,
        validation_time_limit_s=5.0,
        workers=cfg.sandbox_workers,
    )
    _print_validation(report)
    out = run_experiment(cfg, "all", resume=False)
    _print_run(out)
    rep = build_report([out], Path(cfg.results_dir) / "reports")
    print(f"Отчёт: {rep}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from debugmas.report.report import build_report

    runs = [Path(p) for p in args.runs]
    if not runs:
        print(
            'ОШИБКА: укажите запуски: make report RUNS="results/<id1> results/<id2>"',
            file=sys.stderr,
        )
        return 2
    try:
        report = build_report(runs, Path(args.out))
    except ValueError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        return 2
    print(f"Отчёт: {report}")
    return 0


def cmd_case(args: argparse.Namespace) -> int:
    from debugmas.report.cases import render_case

    print(render_case(Path(args.run), args.task))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="debugmas", description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("data", help="загрузить, нормализовать и провалидировать ConDefects")
    s.add_argument("--config", default=str(CONFIGS_DIR / "data.yaml"))
    s.add_argument("--limit", type=int, default=None, help="только первые N задач (отладка)")
    s.add_argument("--task", action="append", help="подготовить выбранный task_id; можно повторять")
    s.add_argument("--out", help="каталог подготовленных задач")
    s.set_defaults(func=cmd_data)

    s = sub.add_parser("split", help="создать манифесты выборок")
    s.add_argument("--preset", default="paper3")
    s.add_argument("--all", action="store_true", help="все пресеты")
    s.add_argument("--data-dir", default="data/processed")
    s.add_argument("--splits-config", default=str(CONFIGS_DIR / "splits.yaml"))
    s.add_argument("--out", default="splits")
    s.set_defaults(func=cmd_split)

    for name, fn in (("run", cmd_run), ("final", cmd_final)):
        s = sub.add_parser(name, help=f"{name}: запуск решателя на выборке")
        s.add_argument("--config", required=True)
        s.add_argument("--set", action="append", help="переопределение: ключ=значение")
        if name == "run":
            s.add_argument("--split", required=True)
            s.add_argument("--task", action="append", help="только эти задачи")
            s.add_argument("--limit", type=int, default=None)
            s.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
        else:
            s.add_argument("--run-tag", required=True)
        s.set_defaults(func=fn)

    s = sub.add_parser("smoke", help="прогон на фикстурах с фейковой LLM")
    s.add_argument("--solver", default="workflow")
    s.add_argument("--config", default=str(CONFIGS_DIR / "smoke.yaml"))
    s.add_argument("--set", action="append")
    s.set_defaults(func=cmd_smoke)

    s = sub.add_parser("report", help="построить report.md по запускам")
    s.add_argument("runs", nargs="*")
    s.add_argument("--out", default="results/reports")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("case", help="хронология решения задачи")
    s.add_argument("--run", required=True)
    s.add_argument("--task", required=True)
    s.set_defaults(func=cmd_case)
    return p


OUTPUT_DIRS = ("data", "results", "splits", ".cache", "tests/fixtures")


def _restore_ownership() -> None:
    """В контейнере команды идут от root; возвращаем файлы владельцу репозитория на хосте."""
    if os.geteuid() != 0:
        return
    st = REPO_ROOT.stat()
    if st.st_uid == 0:
        return
    for name in OUTPUT_DIRS:
        top = REPO_ROOT / name
        if not top.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            for entry in (dirpath, *(os.path.join(dirpath, n) for n in dirnames + filenames)):
                try:
                    if os.lstat(entry).st_uid == 0:
                        os.lchown(entry, st.st_uid, st.st_gid)
                except OSError:
                    pass


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    try:
        return int(args.func(args) or 0)
    finally:
        _restore_ownership()
