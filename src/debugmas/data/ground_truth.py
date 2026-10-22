"""Эталон хранится отдельно от данных, доступных решателям."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class GroundTruth:
    task_id: str
    program_id: str
    fault_lines: list[int]
    fixed_code: str
    fixed_line: str
    difficulty: int | None
    date: str | None


def save_ground_truth(value: GroundTruth, task_dir: Path) -> None:
    (task_dir / "ground_truth.json").write_text(
        json.dumps(asdict(value), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_ground_truth(task_dir: Path) -> GroundTruth:
    return GroundTruth(**json.loads((task_dir / "ground_truth.json").read_text(encoding="utf-8")))
