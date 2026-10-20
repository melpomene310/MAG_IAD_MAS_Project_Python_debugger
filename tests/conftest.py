from __future__ import annotations

from pathlib import Path

import pytest

from debugmas.config import ExperimentConfig
from debugmas.data.condefects import TestSource
from debugmas.data.prepare import prepare_dataset
from debugmas.data.schema import load_agent_view
from debugmas.experiment.tracing import EventSink, TaskTracer
from debugmas.llm.fake import FakeLLM
from debugmas.solvers.base import RunContext, SolverLimits
from debugmas.tools.registry import ToolRegistry

FIXTURES = Path(__file__).parent / "fixtures" / "condefects_mini"
ALL_TOOLS = ["run_tests", "get_test", "run_program", "trace", "submit"]


@pytest.fixture(scope="session")
def fixtures_root() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def processed(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    out = tmp_path_factory.mktemp("processed")
    report = prepare_dataset(
        FIXTURES, TestSource(test_dir=FIXTURES / "Test"), out, seed=42, validation_time_limit_s=5
    )
    return out, report


@pytest.fixture(scope="session")
def data_dir(processed: tuple[Path, dict]) -> Path:
    return processed[0]


@pytest.fixture
def load_view(data_dir: Path):
    return lambda task_id: load_agent_view(data_dir / "tasks" / task_id)


def fixed_code(task_id: str) -> str:
    d = next((FIXTURES / "Code" / task_id / "Python").iterdir())
    if task_id == "fx001_a":
        d = FIXTURES / "Code" / task_id / "Python" / "1001"
    return (d / "correctVersion.py").read_text()


@pytest.fixture
def make_ctx(data_dir: Path):
    def _make(
        script: list[dict],
        solver: str = "workflow",
        tools: list[str] | None = None,
        **overrides,
    ) -> tuple[RunContext, FakeLLM, EventSink]:
        cfg = ExperimentConfig(
            solver=solver, data_dir=str(data_dir), sandbox_workers=4, **overrides
        )
        llm = FakeLLM(script)
        sink = EventSink(None)
        ctx = RunContext(
            llm=llm,
            tools=ToolRegistry(tools or ALL_TOOLS),
            limits=SolverLimits(
                max_attempts=cfg.max_attempts,
                max_steps=cfg.max_steps,
                max_tokens_per_task=cfg.max_tokens_per_task,
                task_timeout_s=cfg.task_timeout_s,
            ),
            tracer=TaskTracer(sink, "test-run", "task", solver),
            config=cfg,
        )
        return ctx, llm, sink

    return _make
