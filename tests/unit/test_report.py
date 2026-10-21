from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from debugmas.cli import cmd_report
from debugmas.report.report import (
    FIRST_ATTEMPT_RULE,
    RunData,
    build_report,
    section_cases,
    validate_pilot_comparison,
)


def _run(solver: str, tasks: tuple[str, ...] = ("a", "b")) -> RunData:
    cfg = {
        "solver": solver,
        "data_dir": "data/pilot/final",
        "split": "dev",
        "split_preset": "paper3",
        "llm_resolved": {
            "model": "test-model",
            "base_url": "http://proxy/v1",
            "temperature": 0,
            "max_output_tokens": 100,
            "reasoning": None,
            "fake": True,
        },
        "max_attempts": 3,
        "max_steps": 30,
        "max_tokens_per_task": 300_000,
        "task_timeout_s": 1800,
        "initial_failing_shown": 2,
        "show_expected_output": True,
    }
    evals = [
        SimpleNamespace(
            task_id=task,
            final_success=solver == "mas_sequential" and task == "a",
            status="solved" if solver == "mas_sequential" and task == "a" else "error",
            failure_reason=None,
            error=None,
        )
        for task in tasks
    ]
    return RunData(
        Path(solver), solver, solver, cfg, {}, evals, {"overall": {"failure_reasons": {}}}
    )


def test_pilot_requires_same_tasks_and_model_settings():
    runs = [_run(name) for name in ("workflow", "single_agent", "mas_sequential")]
    validate_pilot_comparison(runs)
    runs[2].evals.pop()
    with pytest.raises(ValueError, match="набор задач"):
        validate_pilot_comparison(runs)
    runs[2] = _run("mas_sequential")
    runs[2].cfg["llm_resolved"]["base_url"] = "http://other/v1"
    with pytest.raises(ValueError, match="модель и параметры вызовов"):
        validate_pilot_comparison(runs)
    runs[2].cfg["llm_resolved"]["base_url"] = "http://proxy/v1"
    runs[2].cfg["llm_resolved"]["price_output_per_1m"] = 1.0
    with pytest.raises(ValueError, match="тарифы"):
        validate_pilot_comparison(runs)


def test_pilot_report_rejects_mismatch_before_creating_files(tmp_path: Path, monkeypatch):
    runs = [_run(name) for name in ("workflow", "single_agent", "mas_sequential")]
    runs[1].cfg["max_attempts"] = 2
    monkeypatch.setattr("debugmas.report.report.load_run", lambda path: runs[int(path.name)])
    out = tmp_path / "reports"
    with pytest.raises(ValueError, match="лимиты"):
        build_report([Path("0"), Path("1"), Path("2")], out)
    assert not out.exists()


def test_sequential_mas_appears_in_case_comparison():
    lines = section_cases([_run("workflow"), _run("mas_sequential")], [])
    text = "\n".join(lines)
    assert "mas_sequential решил, а workflow нет (1)" in text
    assert "`a`" in text
    assert "`mas_sequential`" in FIRST_ATTEMPT_RULE


def test_report_cli_shows_validation_error(capsys, monkeypatch):
    def fail(*args):
        raise ValueError("различаются набор задач")

    monkeypatch.setattr("debugmas.report.report.build_report", fail)
    assert cmd_report(Namespace(runs=["run1"], out="unused")) == 2
    assert "ОШИБКА: различаются набор задач" in capsys.readouterr().err
