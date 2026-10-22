"""Данные, доступные решателю, и результаты тестов."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class TestCase:
    __test__ = False

    name: str
    input_path: Path
    expected_path: Path
    time_limit_s: float = 2.0

    def read_input(self) -> str:
        return self.input_path.read_text(encoding="utf-8", errors="replace")

    def read_expected(self) -> str:
        return self.expected_path.read_text(encoding="utf-8", errors="replace")

    def input_size(self) -> int:
        return self.input_path.stat().st_size


@dataclass(frozen=True)
class TestResult:
    name: str
    verdict: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    wall_time: float = 0.0
    timed_out: bool = False
    memory_exceeded: bool = False


@dataclass(frozen=True)
class AgentView:
    task_id: str
    program_id: str
    code: str
    tests: list[TestCase]
    initial_results: list[TestResult]

    def test_by_name(self, name: str) -> TestCase | None:
        return next((test for test in self.tests if test.name == name), None)


def save_agent_view(view: AgentView, task_dir: Path) -> None:
    data = asdict(view)
    for test in data["tests"]:
        test["input_path"] = str(Path(test["input_path"]).relative_to(task_dir))
        test["expected_path"] = str(Path(test["expected_path"]).relative_to(task_dir))
    (task_dir / "agent_view.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_agent_view(task_dir: Path) -> AgentView:
    data = json.loads((task_dir / "agent_view.json").read_text(encoding="utf-8"))
    tests = [
        TestCase(
            t["name"],
            task_dir / t["input_path"],
            task_dir / t["expected_path"],
            t["time_limit_s"],
        )
        for t in data["tests"]
    ]
    return AgentView(
        data["task_id"],
        data["program_id"],
        data["code"],
        tests,
        [TestResult(**r) for r in data["initial_results"]],
    )
