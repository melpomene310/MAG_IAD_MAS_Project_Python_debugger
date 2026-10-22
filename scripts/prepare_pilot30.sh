#!/usr/bin/env bash
set -euo pipefail
REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO_DIR"
RAW=${RAW:-data/raw/ConDefects}
TESTS=${TESTS:-data/raw/Test}
OUT=${OUT:-data/pilot/pilot30}
SPLIT=${SPLIT:-splits/pilot30/paper3}
MAKE_CMD=${MAKE_CMD:-make}

[[ -d "$RAW/Code" && -d "$TESTS" ]] || { echo "Run make fetch-tests first." >&2; exit 2; }
python scripts/select_pilot30.py sample --raw "$RAW" --tests "$TESTS" --out "$SPLIT/dev.txt"
ARGS="--out $OUT"
while IFS= read -r task; do ARGS="$ARGS --task $task"; done < "$SPLIT/dev.txt"
"$MAKE_CMD" data ARGS="--fast $ARGS"
OUT="$OUT" SPLIT="$SPLIT" PYTHONPATH=src python - <<'PY'
import json
import os
from pathlib import Path
from debugmas.data.pilot_selection import PAPER3_BINS
from debugmas.data.splits import bin_of
split = Path(os.environ["SPLIT"])
out = Path(os.environ["OUT"])
ids = (split / "dev.txt").read_text().splitlines()
index = {row["task_id"]: row for row in map(json.loads, (out / "index.jsonl").read_text().splitlines())}
missing = set(ids) - set(index)
assert not missing, f"sampled tasks were not prepared: {', '.join(sorted(missing))}"
counts = {
    name: sum(bin_of(index[task]['difficulty'], {name: bounds}) == name for task in ids)
    for name, bounds in PAPER3_BINS.items()
}
assert len(ids) == len(set(ids)) == 30
assert counts == {'easy': 10, 'medium': 10, 'hard': 10}
print(f"Prepared {len(ids)} tasks: {counts}")
PY
