#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 6 ]]; then
    echo "Usage: bash $0 SNAPSHOT DEV_JSONL OUTPUT VENV base checkpoint-N=/path" >&2
    exit 2
fi
exec bash "$(dirname -- "$0")/omni_pl_chat_p1.sh" "$1" "$2" "$3" "$4" evaluate "${@:5}"
