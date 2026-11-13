#!/usr/bin/env bash
# Produce an Academy mixture audit in the offline CPU namespace.
set -euo pipefail
if [[ $# -ne 7 ]]; then
    echo "Usage: bash $0 SNAPSHOT TRAIN DEV TAXONOMY OUTPUT VENV MAX_TOKENS" >&2
    exit 2
fi
exec bash "$(dirname -- "$0")/omni_pl_chat_p1.sh" "$1" "$2" "$5" "$6" audit-mix "$3" "$4" "$7"
