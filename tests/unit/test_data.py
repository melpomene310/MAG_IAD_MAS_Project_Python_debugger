import json
import zipfile
from pathlib import Path

import pytest

from debugmas.data.condefects import TestSource, list_python_tasks, read_difficulty, read_programs
from debugmas.data.ground_truth import load_ground_truth
from debugmas.data.prepare import (
    DataConfig,
    DataError,
    find_test_source,
    load_index,
    prepare_dataset,
)


def test_parse_fixtures(fixtures_root: Path):
    assert "fx001_a" in list_python_tasks(fixtures_root)
    progs = read_programs(fixtures_root, "fx001_a")
    assert {p.program_id for p in progs} == {"1001", "1002"}
    p = next(p for p in progs if p.program_id == "1001")
    assert p.fault_lines == [6]
    assert read_difficulty(fixtures_root)["fx002_b"] == 1500
    assert "fx003_a" not in read_difficulty(fixtures_root)


def test_unknown_difficulty_is_skipped(tmp_path: Path):
    (tmp_path / "difficulty.txt").write_text("a 123\nb unknown\nc -1\n", encoding="utf-8")
    assert read_difficulty(tmp_path) == {"a": 123}


def test_prepare_selected_tasks(fixtures_root: Path, tmp_path: Path):
    out = tmp_path / "processed"
    report = prepare_dataset(
        fixtures_root,
        TestSource(test_dir=fixtures_root / "Test"),
        out,
        task_ids=["fx002_b", "fx001_a", "fx001_a"],
    )
    assert report["n_tasks_total"] == 2
    assert {row["task_id"] for row in load_index(out)} == {"fx001_a", "fx002_b"}
    with pytest.raises(DataError, match="missing"):
        prepare_dataset(
            fixtures_root,
            TestSource(test_dir=fixtures_root / "Test"),
            tmp_path / "bad",
            task_ids=["missing"],
        )


def test_tests_from_dir_and_zip_are_equal(fixtures_root: Path, tmp_path: Path):
    zpath = tmp_path / "Test.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        for f in (fixtures_root / "Test").rglob("*.txt"):
            z.write(f, "Test/" + str(f.relative_to(fixtures_root / "Test")))
    a = TestSource(test_dir=fixtures_root / "Test").load("fx001_a")
    b = TestSource(test_zip=zpath).load("fx001_a")
    assert [(t.name, t.input_data, t.expected) for t in a] == [
        (t.name, t.input_data, t.expected) for t in b
    ]
    assert len(a) == 4 and a[0].name == "01"


def test_drop_reasons(processed):
    _, report = processed
    assert report["n_tasks_total"] == 7
    assert report["n_tasks_kept"] == 5
    tasks = report["tasks"]
    assert tasks["fx003_a"]["programs"]["3101"] == "unknown_difficulty"
    assert tasks["fx002_c"]["kept"] is None
    assert tasks["fx002_c"]["programs"]["2301"] == "faulty_passes_all"
    assert tasks["fx002_c"]["programs"]["2302"] == "not_python3"
    assert sum(report["dropped_tasks_by_reason"].values()) == 2


def test_one_program_per_task(processed):
    out, report = processed
    index = load_index(out)
    assert len({r["task_id"] for r in index}) == len(index) == 5
    row = next(r for r in index if r["task_id"] == "fx001_a")
    assert row["program_id"] == "1001"  # python2-версия отсеяна
    assert report["tasks"]["fx001_a"]["kept"] == "1001"


def test_agent_view_and_ground_truth(processed, load_view):
    out, _ = processed
    view = load_view("fx001_b")
    assert {r.verdict for r in view.initial_results} == {"TLE"}
    assert all(t.time_limit_s >= 2.0 for t in view.tests)
    gt = load_ground_truth(out / "tasks" / "fx001_b")
    assert gt.fault_lines == [5] and gt.fixed_line.strip() == "n //= 10"
    agent_json = json.loads((out / "tasks" / "fx001_b" / "agent_view.json").read_text())
    assert "fixed_code" not in agent_json and "fault_lines" not in agent_json


def test_float_task_tolerance(load_view):
    view = load_view("fx002_a")
    verdicts = {r.name: r.verdict for r in view.initial_results}
    assert verdicts == {"01": "WA", "02": "AC", "03": "WA"}


def test_missing_test_zip_message(tmp_path: Path):
    cfg = DataConfig(
        repo_url="x",
        commit="y",
        raw_dir=tmp_path / "raw",
        test_zip=tmp_path / "Test.zip",
        test_dir=tmp_path / "Test",
        processed_dir=tmp_path / "out",
    )
    with pytest.raises(DataError, match="Test.zip"):
        find_test_source(cfg)
