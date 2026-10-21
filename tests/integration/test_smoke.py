"""End-to-end: `make smoke` для реализованных решателей создаёт файлы и отчёт."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from debugmas.cli import main
from debugmas.report.cases import render_case


@pytest.mark.parametrize("solver", ["workflow", "single_agent", "mas_sequential"])
def test_smoke(solver: str, tmp_path: Path, capsys):
    data_dir, results = tmp_path / "data", tmp_path / "results"
    rc = main(
        [
            "smoke",
            "--solver",
            solver,
            "--set",
            f"data_dir={data_dir}",
            "--set",
            f"results_dir={results}",
        ]
    )
    assert rc == 0
    runs = [p for p in results.iterdir() if p.is_dir() and p.name != "reports"]
    assert len(runs) == 1
    run = runs[0]
    for name in ("config.resolved.yaml", "meta.json", "tasks.jsonl", "trace.jsonl", "metrics.json"):
        assert (run / name).exists(), name
    rows = [json.loads(x) for x in (run / "tasks.jsonl").read_text().splitlines()]
    assert {r["task_id"] for r in rows} == {"fx001_a", "fx001_b", "fx001_c", "fx002_a", "fx002_b"}
    assert all(r["solver"] == solver for r in rows)
    assert (run / "candidates" / "fx001_a" / "attempt_1.py").exists()
    meta = json.loads((run / "meta.json").read_text())
    assert meta["finished"] and meta["fake_llm"] is True
    metrics = json.loads((run / "metrics.json").read_text())
    assert metrics["overall"]["n_tasks"] == 5
    assert metrics["overall"]["final_success"]["k"] >= 4
    reports = list((results / "reports").glob("*/report.md"))
    assert reports
    text = reports[0].read_text()
    for section in ("## 1.", "## 2.", "## 3.", "## 4."):
        assert section in text
    assert "## 5." not in text
    case = render_case(run, "fx001_b")
    assert ">>" in case and "Хронология" in case and "Итог" in case


def test_resume_skips_done(tmp_path: Path):
    from debugmas.config import load_experiment_config
    from debugmas.data.condefects import TestSource
    from debugmas.data.prepare import prepare_dataset
    from debugmas.experiment.runner import run_experiment
    from tests.conftest import FIXTURES

    data_dir = tmp_path / "data"
    prepare_dataset(FIXTURES, TestSource(test_dir=FIXTURES / "Test"), data_dir)
    cfg = load_experiment_config(
        "configs/smoke.yaml", {"data_dir": str(data_dir), "results_dir": str(tmp_path / "r")}
    )
    out1 = run_experiment(cfg, "all", task_filter=["fx001_a", "fx001_c"])
    out_step = run_experiment(cfg, "all", task_filter=["fx001_b"])
    assert out_step == out1
    assert json.loads((out_step / "meta.json").read_text())["n_tasks"] == 3
    assert len((out_step / "tasks.jsonl").read_text().splitlines()) == 3
    out2 = run_experiment(cfg, "all")
    assert out1 == out2
    lines = (out2 / "tasks.jsonl").read_text().splitlines()
    assert len(lines) == 5  # две задачи не перерешивались
    assert json.loads((out2 / "meta.json").read_text())["n_tasks"] == 5
