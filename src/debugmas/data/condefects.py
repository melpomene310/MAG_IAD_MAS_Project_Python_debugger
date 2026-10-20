"""Чтение исходной структуры ConDefects и тестов AtCoder."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Program:
    task_id: str
    program_id: str
    faulty_code: str
    fixed_code: str
    fault_lines: list[int]


@dataclass(frozen=True)
class SourceTest:
    name: str
    input_data: bytes
    expected: bytes


def list_python_tasks(root: Path) -> list[str]:
    return sorted(p.name for p in (root / "Code").iterdir() if (p / "Python").is_dir())


def _metadata(root: Path, name: str, cast):  # noqa: ANN001, ANN202
    path = root / name
    if not path.exists():
        return {}
    return {
        parts[0]: cast(parts[1])
        for line in path.read_text(encoding="utf-8").splitlines()
        if len(parts := line.split(maxsplit=1)) == 2
    }


def read_difficulty(root: Path) -> dict[str, int]:
    return _metadata(root, "difficulty.txt", int)


def read_dates(root: Path) -> dict[str, str]:
    return _metadata(root, "date.txt", str)


def read_programs(root: Path, task_id: str) -> list[Program]:
    base = root / "Code" / task_id / "Python"
    programs = []
    for directory in sorted(p for p in base.iterdir() if p.is_dir()):
        try:
            faulty = (directory / "faultyVersion.py").read_text(encoding="utf-8")
            fixed = (directory / "correctVersion.py").read_text(encoding="utf-8")
            lines = [int(x) for x in (directory / "faultLocation.txt").read_text().split()]
        except (OSError, ValueError):
            continue
        programs.append(Program(task_id, directory.name, faulty, fixed, lines))
    return programs


class TestSource:
    __test__ = False

    def __init__(self, test_dir: Path | None = None, test_zip: Path | None = None):
        self.test_dir = Path(test_dir) if test_dir else None
        self.test_zip = Path(test_zip) if test_zip else None

    def load(self, task_id: str) -> list[SourceTest]:
        contest, letter = task_id.rsplit("_", 1)
        folders = [f"{contest}/{letter.upper()}", f"{contest}/Ex"]
        if self.test_dir:
            for folder in folders:
                base = self.test_dir / folder
                if (base / "in").is_dir():
                    return [
                        SourceTest(p.stem, p.read_bytes(), (base / "out" / p.name).read_bytes())
                        for p in sorted((base / "in").iterdir())
                        if p.is_file() and (base / "out" / p.name).is_file()
                    ]
            return []
        if self.test_zip:
            with zipfile.ZipFile(self.test_zip) as archive:
                names = set(archive.namelist())
                for folder in folders:
                    prefix = f"Test/{folder}/"
                    inputs = sorted(n for n in names if n.startswith(prefix + "in/") and not n.endswith("/"))
                    if inputs:
                        return [
                            SourceTest(
                                Path(n).stem,
                                archive.read(n),
                                archive.read(prefix + "out/" + Path(n).name),
                            )
                            for n in inputs
                            if prefix + "out/" + Path(n).name in names
                        ]
        return []
