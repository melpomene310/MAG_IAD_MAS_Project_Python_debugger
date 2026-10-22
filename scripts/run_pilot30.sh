#!/usr/bin/env bash
set -euo pipefail
REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO_DIR"
DRY_RUN=false
if [[ ${1:-} == --dry-run ]]; then
  DRY_RUN=true
fi
MANIFEST=${MANIFEST:-splits/pilot30/paper3/dev.txt}
RESULTS_DIR=${RESULTS_DIR:-results/pilot30_live}
MAX_COST=${MAX_COST:-2.00}
COMMON="--set data_dir=data/pilot/pilot30 --set splits_dir=splits/pilot30 --set results_dir=$RESULTS_DIR --set max_attempts=3 --set max_tokens_per_task=60000 --set task_timeout_s=900 --set max_steps=30 --set initial_failing_shown=4 --set tool_response_max_chars=8000 --set context_keep_steps=12 --set llm.temperature=0 --set llm.max_output_tokens=4096 --set llm.reasoning.enabled=false --set llm.max_retries=0 --set llm.cache_enabled=false --set concurrency=1"
[[ -f "$MANIFEST" ]] || { echo "Run scripts/prepare_pilot30.sh first." >&2; exit 2; }
if $DRY_RUN; then
  printf 'max_cost=$%s\nparameters: %s\n' "$MAX_COST" "$COMMON"
  while IFS= read -r task; do
    for solver in workflow single_agent mas_sequential; do
      printf 'task=%s solver=%s\n' "$task" "$solver"
    done
  done < "$MANIFEST"
  exit 0
fi
[[ -f .env.openrouter ]] || { echo "Missing .env.openrouter." >&2; exit 2; }
while IFS= read -r task; do
  if ! python - "$RESULTS_DIR" "$MAX_COST" <<'PY'
import json, sys
from pathlib import Path
total=sum(json.loads(p.read_text())['overall']['costs']['cost_total'] for p in Path(sys.argv[1]).glob('*/metrics.json')) if Path(sys.argv[1]).exists() else 0
print(f'cost before {total:.6f}')
sys.exit(0 if total < float(sys.argv[2]) else 1)
PY
  then
    echo "Reached the observed budget of \$$MAX_COST; stopping before task $task."
    break
  fi
  for config in configs/workflow.yaml configs/single_agent.yaml configs/mas_sequential.yaml; do
    make run PROFILE=openrouter CONFIG="$config" SPLIT=dev ARGS="$COMMON --task $task" < /dev/null
  done
  python - "$RESULTS_DIR" <<'PY'
import json, sys
from pathlib import Path
rows=[json.loads(p.read_text())['overall'] for p in Path(sys.argv[1]).glob('*/metrics.json')]
print(
    'after task: cost=$%.6f solved=%d/%d tokens=%d time=%.1fs'
    % (
        sum(x['costs']['cost_total'] for x in rows),
        sum(x['final_success']['k'] for x in rows),
        sum(x['n_tasks'] for x in rows),
        sum(x['costs']['tokens']['total'] for x in rows),
        sum(x['time']['total'] for x in rows),
    )
)
PY
done < "$MANIFEST"
