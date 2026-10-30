#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
echo "Deprecated: use make start PROFILE=light (compatibility alias removed next release)." >&2
PROFILE=light exec "${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}" "$ROOT_DIR/scripts/dev/stack_profile.py" start
