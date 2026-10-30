#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/python_contract.sh
source "$ROOT_DIR/scripts/lib/python_contract.sh"
echo "Deprecated: use make start PROFILE=light (compatibility alias removed next release)." >&2
PROFILE=light exec "$(venom_python_bin "$ROOT_DIR")" "$ROOT_DIR/scripts/dev/stack_profile.py" start
