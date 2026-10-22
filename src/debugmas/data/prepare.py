"""Проверка программ и подготовка задач для решателей."""

from __future__ import annotations

import ast
import json
import random
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from debugmas.data.condefects import (
    Program,
    SourceTest,
    TestSource,
    list_python_tasks,
    read_dates,
    read_difficulty,
    read_programs,
)
from debugmas.data.ground_truth import GroundTruth, save_ground_truth
from debugmas.data.schema import AgentView, TestCase, save_agent_view
from debugmas.sandbox.compare import judge
from debugmas.sandbox.runner import run_program, run_tests


class DataError(RuntimeError):
    pass


@dataclass(frozen=True)
class DataConfig:
    repo_url: str
    commit: str
    raw_dir: Path
    test_zip: Path
    test_dir: Path
    processed_dir: Path
    seed: int = 42
    validation_time_limit_s: float = 10.0
    memory_mb: int = 1024
    workers: int = 16
    fast: bool = False
    limit_tasks: int | None = None
    task_ids: list[str] | None = None

    @classmethod
    def from_dict(cls, data: dict) -> DataConfig:
        return cls(
            **{
                key: Path(value)
                if key in {"raw_dir", "test_zip", "test_dir", "processed_dir"}
                else value
                for key, value in data.items()
            }
        )


def find_test_source(cfg: DataConfig) -> TestSource:
    if cfg.test_dir.is_dir():
        return TestSource(test_dir=cfg.test_dir)
    if cfg.test_zip.is_file():
        return TestSource(test_zip=cfg.test_zip)
    raise DataError(
        f"Тесты не найдены: положите Test.zip в {cfg.test_zip} или выполните make fetch-tests"
    )


def load_index(processed_dir: Path) -> list[dict]:
    path = processed_dir / "index.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _syntax_reason(program: Program) -> str | None:
    try:
        ast.parse(program.faulty_code)
        ast.parse(program.fixed_code)
    except SyntaxError:
        return "not_python3"
    return None


def _missing_library(stderr: str) -> str | None:
    match = re.search(
        r"(?:ModuleNotFoundError|ImportError): No module named ['\"]([^'\"]+)", stderr
    )
    return match.group(1).split(".")[0] if match else None


def _validate_program(
    program: Program,
    source_tests: list[SourceTest],
    limit: float,
    memory_mb: int,
    workers: int,
    task_dir: Path,
) -> tuple[str | None, AgentView | None, list[float]]:
    reason = _syntax_reason(program)
    if reason:
        return reason, None, []
    task_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = task_dir / "tests"
    tests_dir.mkdir(exist_ok=True)
    tests = []
    fixed_times = []
    for source in source_tests:
        input_path = tests_dir / f"{source.name}.in"
        expected_path = tests_dir / f"{source.name}.out"
        input_path.write_bytes(source.input_data)
        expected_path.write_bytes(source.expected)
        fixed = run_program(program.fixed_code, source.input_data, limit, memory_mb)
        missing = _missing_library(fixed.stderr)
        if missing:
            return f"missing_library:{missing}", None, []
        if judge(fixed, source.expected.decode("utf-8", errors="replace")) != "AC":
            return "fixed_fails_tests", None, []
        fixed_times.append(fixed.wall_time)
        tests.append(
            TestCase(source.name, input_path, expected_path, max(2.0, 3 * fixed.wall_time))
        )
    initial = run_tests(program.faulty_code, tests, workers=workers, memory_mb=memory_mb)
    if all(result.verdict == "AC" for result in initial):
        return "faulty_passes_all", None, []
    return (
        None,
        AgentView(program.task_id, program.program_id, program.faulty_code, tests, initial),
        fixed_times,
    )


def _prepare_fast_program(
    program: Program,
    source_tests: list[SourceTest],
    memory_mb: int,
    workers: int,
    task_dir: Path,
) -> tuple[str | None, AgentView | None]:
    """Prepare one faulty version without executing its corrected counterpart."""
    reason = _syntax_reason(program)
    if reason:
        return reason, None
    task_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = task_dir / "tests"
    tests_dir.mkdir(exist_ok=True)
    tests = []
    for source in source_tests:
        input_path = tests_dir / f"{source.name}.in"
        expected_path = tests_dir / f"{source.name}.out"
        input_path.write_bytes(source.input_data)
        expected_path.write_bytes(source.expected)
        tests.append(TestCase(source.name, input_path, expected_path))
    initial = run_tests(program.faulty_code, tests, workers=workers, memory_mb=memory_mb)
    if all(result.verdict == "AC" for result in initial):
        return "faulty_passes_all", None
    return None, AgentView(program.task_id, program.program_id, program.faulty_code, tests, initial)


def prepare_dataset(
    root: Path,
    test_source: TestSource,
    out: Path,
    *,
    seed: int = 42,
    validation_time_limit_s: float = 10.0,
    memory_mb: int = 1024,
    workers: int = 16,
    fast: bool = False,
    limit_tasks: int | None = None,
    task_ids: list[str] | None = None,
) -> dict:
    root, out = Path(root), Path(out)
    if not (root / "Code").is_dir():
        raise DataError(f"Нет каталога ConDefects/Code: {root}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "tasks").mkdir(exist_ok=True)
    difficulties, dates = read_difficulty(root), read_dates(root)
    tasks = list_python_tasks(root)
    if task_ids is not None:
        unknown = sorted(set(task_ids) - set(tasks))
        if unknown:
            raise DataError(f"Задачи не найдены в ConDefects: {', '.join(unknown)}")
        tasks = sorted(set(task_ids))
    if limit_tasks is not None:
        tasks = tasks[:limit_tasks]
    report: dict = {"n_tasks_total": len(tasks), "tasks": {}}
    index = []
    program_reasons: Counter[str] = Counter()
    dropped_reasons: Counter[str] = Counter()
    for task_id in tasks:
        item: dict = {"kept": None, "programs": {}}
        report["tasks"][task_id] = item
        programs = read_programs(root, task_id)
        difficulty = difficulties.get(task_id)
        source_tests = test_source.load(task_id)
        if difficulty is None:
            for program in programs:
                item["programs"][program.program_id] = "unknown_difficulty"
                program_reasons["unknown_difficulty"] += 1
            dropped_reasons["unknown_difficulty"] += 1
            continue
        if not source_tests:
            for program in programs:
                item["programs"][program.program_id] = "no_tests"
                program_reasons["no_tests"] += 1
            dropped_reasons["no_tests"] += 1
            continue
        valid: list[tuple[Program, AgentView, list[float] | None]] = []
        candidates = programs.copy()
        for program in candidates:
            task_dir = out / "tasks" / task_id
            if fast:
                reason, view = _prepare_fast_program(
                    program, source_tests, memory_mb, workers, task_dir
                )
                times = None
            else:
                reason, view, times = _validate_program(
                    program, source_tests, validation_time_limit_s, memory_mb, workers, task_dir
                )
            if reason:
                item["programs"][program.program_id] = reason
                program_reasons[reason] += 1
            else:
                valid.append((program, view, times))
                if fast:
                    break
        if not valid:
            dropped_reasons["no_valid_program"] += 1
            shutil.rmtree(out / "tasks" / task_id, ignore_errors=True)
            continue
        program, view, times = random.Random(f"{seed}:{task_id}").choice(valid)
        item["kept"] = program.program_id
        task_dir = out / "tasks" / task_id
        save_agent_view(view, task_dir)
        lines = program.fixed_code.splitlines()
        fixed_line = (
            lines[program.fault_lines[0] - 1]
            if program.fault_lines and 0 < program.fault_lines[0] <= len(lines)
            else ""
        )
        save_ground_truth(
            GroundTruth(
                task_id,
                program.program_id,
                program.fault_lines,
                program.fixed_code,
                fixed_line,
                difficulty,
                dates.get(task_id),
            ),
            task_dir,
        )
        if times is not None:
            (task_dir / "fixed_times.json").write_text(
                json.dumps(dict(zip((t.name for t in view.tests), times, strict=True)), indent=2),
                encoding="utf-8",
            )
        index.append(
            {
                "task_id": task_id,
                "program_id": program.program_id,
                "difficulty": difficulty,
                "date": dates.get(task_id),
                "n_tests": len(view.tests),
            }
        )
    report.update(
        {
            "n_tasks_kept": len(index),
            "n_tasks_dropped": len(tasks) - len(index),
            "dropped_tasks_by_reason": dict(dropped_reasons),
            "programs_by_reason": dict(program_reasons),
            "missing_libraries": {
                key.removeprefix("missing_library:"): value
                for key, value in program_reasons.items()
                if key.startswith("missing_library:")
            },
        }
    )
    (out / "index.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in index), encoding="utf-8"
    )
    (out / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def run_data(cfg: DataConfig) -> dict:
    source = find_test_source(cfg)
    if not cfg.raw_dir.is_dir():
        cfg.raw_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", cfg.repo_url, str(cfg.raw_dir)], check=True)
    current = subprocess.run(
        ["git", "-C", str(cfg.raw_dir), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if current != cfg.commit:
        subprocess.run(["git", "-C", str(cfg.raw_dir), "fetch", "origin", cfg.commit], check=True)
        subprocess.run(["git", "-C", str(cfg.raw_dir), "checkout", cfg.commit], check=True)
    return prepare_dataset(
        cfg.raw_dir,
        source,
        cfg.processed_dir,
        seed=cfg.seed,
        validation_time_limit_s=cfg.validation_time_limit_s,
        memory_mb=cfg.memory_mb,
        workers=cfg.workers,
        fast=cfg.fast,
        limit_tasks=cfg.limit_tasks,
        task_ids=cfg.task_ids,
    )
