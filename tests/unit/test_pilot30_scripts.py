from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).parents[2]


def test_run_pilot30_dry_run_lists_each_solver_per_task(tmp_path: Path) -> None:
    manifest = tmp_path / "dev.txt"
    manifest.write_text("abc001_a\nabc002_b\n", encoding="utf-8")

    completed = subprocess.run(
        ["bash", "scripts/run_pilot30.sh", "--dry-run"],
        check=True,
        cwd=REPO,
        env=os.environ | {"MANIFEST": str(manifest), "MAX_COST": "2.00"},
        capture_output=True,
        text=True,
    )

    assert "max_cost=$2.00" in completed.stdout
    assert "max_tokens_per_task=60000" in completed.stdout
    assert completed.stdout.splitlines()[-6:] == [
        "task=abc001_a solver=workflow",
        "task=abc001_a solver=single_agent",
        "task=abc001_a solver=mas_sequential",
        "task=abc002_b solver=workflow",
        "task=abc002_b solver=single_agent",
        "task=abc002_b solver=mas_sequential",
    ]


def test_run_pilot30_keeps_manifest_stdin_for_the_loop() -> None:
    script = (REPO / "scripts" / "run_pilot30.sh").read_text(encoding="utf-8")

    assert 'ARGS="$COMMON --task $task" < /dev/null' in script


def test_prepare_pilot30_uses_fixture_data_without_network(tmp_path: Path) -> None:
    raw = tmp_path / "raw" / "ConDefects"
    tests = tmp_path / "raw" / "Test"
    out = tmp_path / "data" / "pilot30"
    split = tmp_path / "splits" / "paper3"
    difficulties = {
        **{f"easy_{number}": 10 for number in range(8)},
        **{f"medium_{number}": 500 for number in range(8)},
        **{f"hard_{number}": 1500 for number in range(8)},
        "abc223_a": 6,
        "abc224_b": 81,
        "abc225_d": 778,
        "abc223_d": 1069,
        "abc223_e": 1510,
        "abc223_f": 1641,
    }
    (raw / "difficulty.txt").parent.mkdir(parents=True)
    (raw / "difficulty.txt").write_text(
        "".join(f"{task} {difficulty}\n" for task, difficulty in difficulties.items()),
        encoding="utf-8",
    )
    for task in difficulties:
        contest, letter = task.rsplit("_", 1)
        (raw / "Code" / task / "Python").mkdir(parents=True)
        test = tests / contest / letter.upper()
        (test / "in").mkdir(parents=True)
        (test / "out").mkdir()
        (test / "in" / "sample.in").write_text("1\n")
        (test / "out" / "sample.in").write_text("1\n")

    fake_make = tmp_path / "fake-make.py"
    fake_make.write_text(
        """#!/usr/bin/env python3
import json
import os
import shlex
import sys
from pathlib import Path

args = shlex.split(sys.argv[2].removeprefix('ARGS='))
out = Path(args[args.index('--out') + 1])
difficulty = {}
for line in (Path(os.environ['FAKE_RAW']) / 'difficulty.txt').read_text().splitlines():
    task, value = line.split()
    difficulty[task] = int(value)
tasks = [args[index + 1] for index, value in enumerate(args) if value == '--task']
out.mkdir(parents=True, exist_ok=True)
rows = [json.dumps({'task_id': task, 'difficulty': difficulty[task]}) for task in tasks]
(out / 'index.jsonl').write_text('\\n'.join(rows) + '\\n')
""",
        encoding="utf-8",
    )
    fake_make.chmod(0o755)
    completed = subprocess.run(
        ["bash", "scripts/prepare_pilot30.sh"],
        check=True,
        cwd=REPO,
        env=os.environ
        | {
            "RAW": str(raw),
            "TESTS": str(tests),
            "OUT": str(out),
            "SPLIT": str(split),
            "MAKE_CMD": str(fake_make),
            "FAKE_RAW": str(raw),
        },
        capture_output=True,
        text=True,
    )

    manifest = (split / "dev.txt").read_text(encoding="utf-8").splitlines()
    assert "Prepared 30 tasks" in completed.stdout
    assert len(manifest) == len(set(manifest)) == 30
    assert {"abc223_a", "abc224_b", "abc225_d", "abc223_d", "abc223_e", "abc223_f"} <= set(manifest)
