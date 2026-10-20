"""Повторяемое стратифицированное разбиение задач."""

from __future__ import annotations

import logging
import random
from pathlib import Path

log = logging.getLogger(__name__)


def bin_of(difficulty: int | None, bins: dict[str, list[int | None]]) -> str | None:
    if difficulty is None:
        return None
    for name, (low, high) in bins.items():
        if low is not None and difficulty >= low and (high is None or difficulty < high):
            return name
    return None


def make_splits(
    index: list[dict],
    bins: dict[str, list[int | None]],
    sizes: dict[str, int | str],
    seed: int,
    preset: str,
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"dev": [], "val": [], "test": []}
    for name in bins:
        ids = sorted(row["task_id"] for row in index if bin_of(row.get("difficulty"), bins) == name)
        random.Random(f"{preset}:{seed}:{name}").shuffle(ids)
        n_val, n_test = int(sizes["val"]), int(sizes["test"])
        if len(ids) < n_val + n_test:
            n_val = round(len(ids) * n_val / (n_val + n_test))
            n_test = len(ids) - n_val
            log.warning("Размеры выборок для %s уменьшены: val=%d, test=%d", name, n_val, n_test)
        result["val"].extend(ids[:n_val])
        result["test"].extend(ids[n_val : n_val + n_test])
        result["dev"].extend(ids[n_val + n_test :])
    return {name: sorted(ids) for name, ids in result.items()}


def write_manifests(splits: dict[str, list[str]], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, ids in splits.items():
        (directory / f"{name}.txt").write_text("".join(f"{task}\n" for task in ids), encoding="utf-8")


def read_manifest(root: Path, preset: str, split: str) -> list[str]:
    return (root / preset / f"{split}.txt").read_text(encoding="utf-8").splitlines()
