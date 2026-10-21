"""Committed pilot outputs remain complete and safe visualizer fixtures."""

from __future__ import annotations

import json
import re

from debugmas.config import REPO_ROOT

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "run_outputs" / "english_pilot"
TASK_IDS = {"abc223_a", "abc223_d", "abc223_e", "abc223_f", "abc224_b", "abc225_d"}
RUNS = {
    "20261021_workflow_dev_2e0f4b7c": ("workflow", 30),
    "20261021_single_agent_dev_4381d703": ("single_agent", 105),
    "20261021_mas_sequential_dev_9615146d": ("mas_sequential", 93),
}
FORBIDDEN_SECRET = re.compile(r"sk-or-v1-|OPENAI_API_KEY|Authorization: Bearer")
LOCAL_PATH = re.compile(r"/(?:home|app|tmp|root)(?:/[^\s\"']*)?")


def test_pilot_outputs_are_complete() -> None:
    for run_id, (solver, event_count) in RUNS.items():
        run_dir = FIXTURES / run_id
        assert {
            "config.resolved.yaml",
            "meta.json",
            "metrics.json",
            "tasks.jsonl",
            "trace.jsonl",
            "candidates",
        } <= {path.name for path in run_dir.iterdir()}

        tasks = [json.loads(line) for line in (run_dir / "tasks.jsonl").read_text().splitlines()]
        events = [json.loads(line) for line in (run_dir / "trace.jsonl").read_text().splitlines()]
        assert {task["task_id"] for task in tasks} == TASK_IDS
        assert len(tasks) == len(TASK_IDS)
        assert len(events) == event_count
        assert {event["task_id"] for event in events} == TASK_IDS
        assert {event["solver"] for event in events} == {solver}


def test_pilot_outputs_contain_no_secrets_and_only_the_known_cache_path() -> None:
    local_paths: set[str] = set()
    for path in FIXTURES.rglob("*"):
        if path.is_file() and path.name != "README.md":
            text = path.read_text(encoding="utf-8")
            assert not FORBIDDEN_SECRET.search(text), path
            local_paths.update(LOCAL_PATH.findall(text))
    assert local_paths == {"/app/.cache/llm"}
