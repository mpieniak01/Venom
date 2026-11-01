#!/usr/bin/env bash
set -euo pipefail
[[ $# -ge 2 ]] || { echo 'Usage: train.sh CONFIG.yml lora|qlora|full [RESUME_CHECKPOINT]' >&2; exit 2; }
CONFIG=$(realpath -- "$1")
MODE=$2
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source /workspace/data/vast-training/env.sh
python "$SCRIPT_DIR/doctor.py" --mode "$MODE" --output /workspace/data/vast-training/logs/preflight.json
RUN_DIR=$(dirname -- "$CONFIG")
exec 9>"$RUN_DIR/training.lock"
flock -n 9 || { echo 'This run is already active.' >&2; exit 1; }
ARGS=(train "$CONFIG")
if [[ $# -ge 3 ]]; then ARGS+=(--resume-from-checkpoint "$(realpath -- "$3")"); fi
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
python -m pip freeze > "$RUN_DIR/packages-$STAMP.txt"
cp -- "$SCRIPT_DIR/stack.json" "$RUN_DIR/stack-$STAMP.json"
axolotl "${ARGS[@]}" 2>&1 | tee "$RUN_DIR/train-$STAMP.log"
