#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "🧭 Low-memory profile overrides:"
echo "  - ACTIVE_LLM_SERVER=none"
echo "  - LLM_WARMUP_ON_STARTUP=false"
echo "  - VENOM_PAUSE_BACKGROUND_TASKS=true"
echo "  - ENABLE_AUTO_DOCUMENTATION=false"
echo "  - ENABLE_AUTO_GARDENING=false"
echo "  - ENABLE_HEALTH_CHECKS=false"

MAKE_BIN="${MAKE:-make}"

ACTIVE_LLM_SERVER=none \
LLM_WARMUP_ON_STARTUP=false \
VENOM_PAUSE_BACKGROUND_TASKS=true \
ENABLE_AUTO_DOCUMENTATION=false \
ENABLE_AUTO_GARDENING=false \
ENABLE_HEALTH_CHECKS=false \
ALLOW_DEGRADED_START=1 \
"$MAKE_BIN" --no-print-directory _start START_MODE=dev START_WEB_MODE=webpack
