#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
PYTHON=/workspace/axolotl-venv/bin/python
[[ -x "$PYTHON" ]] || { echo 'Expected Axolotl cloud image venv is missing.' >&2; exit 1; }
ROOT=/workspace/data/vast-training
mkdir -p "$ROOT"/{datasets,outputs,logs,configs}
cat > "$ROOT/env.sh" <<'ENV'
export PATH=/workspace/axolotl-venv/bin:$PATH
export HF_HOME=/workspace/data/huggingface-cache
export HF_DATASETS_CACHE=/workspace/data/huggingface-cache/datasets
export TOKENIZERS_PARALLELISM=false
export WANDB_MODE=disabled
ENV
source "$ROOT/env.sh"
"$PYTHON" doctor.py --mode "${1:-qlora}" --output "$ROOT/logs/environment.json"
echo ready > "$ROOT/environment.state"
echo 'Environment ready; upload dataset and generate a training config. Training was not started.'
