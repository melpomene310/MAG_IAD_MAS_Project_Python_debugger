#!/usr/bin/env bash
# Runs the six-task English-interface pilot for all three solvers.
# Requires a local, ignored .env.openrouter with OPENAI_API_KEY configured.
# A repeated invocation resumes unfinished solver runs; it does not spend calls on completed tasks.

set -euo pipefail

REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO_DIR"

if [[ ! -f .env.openrouter ]]; then
    echo "Missing .env.openrouter. Copy .env.openrouter.example and set OPENAI_API_KEY locally." >&2
    exit 2
fi

PILOT_ARGS='--set data_dir=data/pilot/final --set splits_dir=splits/pilot --set results_dir=results/pilot_live --set max_tokens_per_task=30000 --set task_timeout_s=600 --set max_steps=30 --set llm.max_output_tokens=4096 --set llm.max_retries=0 --set llm.cache_enabled=false --set concurrency=1'

for CONFIG in configs/workflow.yaml configs/single_agent.yaml configs/mas_sequential.yaml; do
    echo "Running $CONFIG on the six-task English pilot..."
    make run PROFILE=openrouter CONFIG="$CONFIG" SPLIT=dev ARGS="$PILOT_ARGS"
done

echo "Pilot runs are in results/pilot_live/. Build the comparison report with:"
echo "make report RUNS=\"results/pilot_live/<workflow-run> results/pilot_live/<single-agent-run> results/pilot_live/<mas-run>\""
