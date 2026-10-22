#!/usr/bin/env python3
"""Create the manifest for the 30-task ConDefects pilot."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# The preparation script is invoked on the host so it can inspect local data.
# Make the package import work without requiring a host-side installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from debugmas.data.pilot_selection import (
    PILOT30_PER_BIN,
    available_tasks,
    select_candidates,
)


def write_ids(path: Path, ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{task}\n" for task in ids), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sample = sub.add_parser("sample")
    sample.add_argument("--raw", type=Path, required=True)
    sample.add_argument("--tests", type=Path, required=True)
    sample.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    tasks = available_tasks(args.raw, args.tests)
    ids = select_candidates(tasks, set(tasks), per_bin=PILOT30_PER_BIN)
    write_ids(args.out, ids)
    print(f"sample: {len(ids)} ({PILOT30_PER_BIN} per bin)")


if __name__ == "__main__":
    main()
