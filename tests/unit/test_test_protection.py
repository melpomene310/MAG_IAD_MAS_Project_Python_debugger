from pathlib import Path

import pytest

from debugmas.config import ExperimentConfig
from debugmas.experiment import runner
from debugmas.experiment.runner import RunError, run_experiment, run_final


def test_run_rejects_test_split(data_dir: Path, tmp_path: Path):
    cfg = ExperimentConfig(data_dir=str(data_dir), results_dir=str(tmp_path))
    with pytest.raises(RunError, match="make final"):
        run_experiment(cfg, "test")


def test_cli_run_rejects_test_split(capsys):
    from debugmas.cli import main

    assert main(["run", "--config", "configs/workflow.yaml", "--split", "test"]) == 2
    assert "make final" in capsys.readouterr().err


def test_final_rejects_dirty_tree(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(runner, "git_info", lambda: {"commit": "abc", "dirty": True})
    with pytest.raises(RunError, match="не чистое"):
        run_final(ExperimentConfig(results_dir=str(tmp_path)), "tag1")


def test_final_rejects_existing_tag(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(runner, "git_info", lambda: {"commit": "abc", "dirty": False})
    (tmp_path / "final" / "tag1").mkdir(parents=True)
    with pytest.raises(RunError, match="уже существует"):
        run_final(ExperimentConfig(results_dir=str(tmp_path)), "tag1")


def test_final_forbids_filters(data_dir: Path, tmp_path: Path):
    cfg = ExperimentConfig(data_dir=str(data_dir), results_dir=str(tmp_path))
    with pytest.raises(RunError, match="запрещены"):
        run_experiment(cfg, "test", final=True, limit=3)


def test_final_disables_cache(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(runner, "git_info", lambda: {"commit": "abc", "dirty": False})
    seen = {}

    def fake_run(cfg, split, **kw):
        seen.update(cache=cfg.llm.cache_enabled, split=split, **kw)
        return kw["out_dir"]

    monkeypatch.setattr(runner, "run_experiment", fake_run)
    out = run_final(ExperimentConfig(results_dir=str(tmp_path)), "tag2")
    assert seen["cache"] is False and seen["split"] == "test" and seen["final"] is True
    assert out == tmp_path / "final" / "tag2"
