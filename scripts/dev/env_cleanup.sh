#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-safe}"
ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

CONFIRM_DEEP_CLEAN="${CONFIRM_DEEP_CLEAN:-0}"
DRY_RUN="${DRY_RUN:-0}"

PROTECTED_PATTERNS=(
  "models"
  ".venv"
  "data"
  "data/"
)

SAFE_TARGETS=(
  ".pytest_cache"
  ".mypy_cache"
  ".ruff_cache"
  "web-next/.next"
  "web-next/.turbo"
  "web-next/.cache"
  "web-next/.eslintcache"
  "web-next/coverage"
  "test-results"
  "htmlcov"
)

DEEP_EXTRA_TARGETS=(
  "web-next/node_modules"
  ".next"
)

is_protected() {
  local rel="$1"
  for p in "${PROTECTED_PATTERNS[@]}"; do
    if [[ "$rel" == "$p" || "$rel" == "$p"/* ]]; then
      return 0
    fi
  done
  return 1
}

rm_target() {
  local rel="$1"
  local abs="$ROOT_DIR/$rel"

  if is_protected "$rel"; then
    echo "⛔ Skip protected: $rel"
    return 0
  fi

  if [[ ! -e "$abs" ]]; then
    echo "ℹ️  Missing: $rel"
    return 0
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[dry-run] rm -rf $abs"
    return 0
  fi

  rm -rf "$abs"
  echo "🧹 Removed: $rel"
}

run_mode_safe() {
  for rel in "${SAFE_TARGETS[@]}"; do
    rm_target "$rel"
  done
}

run_mode_deep() {
  if [[ "$CONFIRM_DEEP_CLEAN" != "1" ]]; then
    echo "❌ Deep clean blocked. Use CONFIRM_DEEP_CLEAN=1"
    exit 1
  fi

  run_mode_safe
  for rel in "${DEEP_EXTRA_TARGETS[@]}"; do
    rm_target "$rel"
  done
}

case "$MODE" in
  safe)
    run_mode_safe
    ;;
  deep)
    run_mode_deep
    ;;
  *)
    echo "Usage: scripts/dev/env_cleanup.sh [safe|deep]"
    exit 2
    ;;
esac

echo "✅ env_cleanup completed (mode=$MODE, dry_run=$DRY_RUN)"
