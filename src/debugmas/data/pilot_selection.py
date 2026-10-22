"""Детерминированный отбор задач для быстрого пилота."""

from __future__ import annotations

import random
from pathlib import Path

from debugmas.data.condefects import list_python_tasks, read_difficulty
from debugmas.data.splits import bin_of

PILOT30_SEED = 42
PILOT30_PER_BIN = 10
PILOT30_EXISTING = {
    "abc223_a",
    "abc223_d",
    "abc223_e",
    "abc223_f",
    "abc224_b",
    "abc225_d",
}
PAPER3_BINS = {"easy": [0, 400], "medium": [400, 1300], "hard": [1300, None]}


def has_directory_tests(test_dir: Path, task_id: str) -> bool:
    contest, letter = task_id.rsplit("_", 1)
    for name in (letter.upper(), "Ex"):
        base = test_dir / contest / name
        inputs = base / "in"
        outputs = base / "out"
        if (
            inputs.is_dir()
            and outputs.is_dir()
            and any(path.is_file() and (outputs / path.name).is_file() for path in inputs.iterdir())
        ):
            return True
    return False


def select_candidates(
    task_difficulties: dict[str, int],
    available_ids: set[str],
    *,
    per_bin: int = PILOT30_PER_BIN,
    seed: int = PILOT30_SEED,
) -> list[str]:
    """Include prior pilot tasks, then sample a fixed seeded manifest per bin."""
    chosen: list[str] = []
    for name, bounds in PAPER3_BINS.items():
        ids = sorted(
            task
            for task in available_ids
            if bin_of(task_difficulties.get(task), {name: bounds}) == name
        )
        required = sorted(PILOT30_EXISTING & set(ids))
        if len(required) > per_bin:
            raise ValueError(f"too many required {name} tasks")
        rest = [task for task in ids if task not in required]
        random.Random(f"pilot30:{seed}:{name}").shuffle(rest)
        selected = required + rest[: per_bin - len(required)]
        if len(selected) < per_bin:
            raise ValueError(f"not enough test-backed {name} tasks: {len(selected)}/{per_bin}")
        chosen.extend(selected)
    return chosen


def available_tasks(raw_dir: Path, test_dir: Path) -> dict[str, int]:
    difficulty = read_difficulty(raw_dir)
    return {
        task: difficulty[task]
        for task in list_python_tasks(raw_dir)
        if task in difficulty and has_directory_tests(test_dir, task)
    }
