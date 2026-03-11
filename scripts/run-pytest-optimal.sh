#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/venom
if [[ ! -f ".venv/bin/activate" ]]; then
  echo "ERROR: missing virtualenv activation script (.venv/bin/activate). Create .venv first."
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

FAST_GROUP_FILE="config/pytest-groups/fast.txt"
HEAVY_GROUP_FILE="config/pytest-groups/heavy.txt"
LONG_GROUP_FILE="config/pytest-groups/long.txt"
MANUAL_LONG_RUNNING_FILE="${MANUAL_LONG_RUNNING_FILE:-config/pytest-groups/manual-long-running.txt}"
PYTEST_AUTO_MARK_EXPR="${PYTEST_AUTO_MARK_EXPR:-not manual_llm and not performance}"
PYTEST_HEAVY_MARK_EXPR="${PYTEST_HEAVY_MARK_EXPR:-not manual_llm}"

# make test should be deterministic and not inherit external marker filters
# that can accidentally deselect whole groups (e.g. performance/smoke).
unset PYTEST_ADDOPTS
unset PYTEST_MARKEXPR

# Globalna polityka: testy nie uruchamiają kontenerów sandbox.
export ENABLE_SANDBOX=false
export ALLOW_SANDBOX_CONTAINERS=false

read_group_tests() {
  local file="$1"
  grep -vE '^\s*(#|$)' "$file"
}

read_group_tests_filtered() {
  local file="$1"
  local tests
  tests="$(read_group_tests "$file" || true)"
  if [[ -z "$tests" ]]; then
    return 0
  fi
  if [[ ! -f "$MANUAL_LONG_RUNNING_FILE" ]]; then
    printf '%s\n' "$tests"
    return 0
  fi
  printf '%s\n' "$tests" | grep -vxF -f "$MANUAL_LONG_RUNNING_FILE" || true
}

run_group() {
  local group_name="$1"
  local workers="$2"
  local group_file="$3"
  local mark_expr="$4"
  local tests

  echo "▶️  Pytest group: ${group_name}"
  tests="$(read_group_tests_filtered "${group_file}")"
  if [[ -z "$tests" ]]; then
    echo "ℹ️  Group ${group_name}: no tests after manual-long-running exclusion list."
    return 0
  fi
  set +e
  pytest -n "$workers" -m "$mark_expr" $tests
  local rc=$?
  set -e
  if [[ $rc -eq 5 ]]; then
    echo "ℹ️  Group ${group_name}: no tests selected after mark filter (${mark_expr})."
    return 0
  fi
  return "$rc"
}

# Full pytest suite using environment-optimized worker counts (sequential).
run_group "heavy" 1 "${HEAVY_GROUP_FILE}" "$PYTEST_HEAVY_MARK_EXPR"
run_group "long" 2 "${LONG_GROUP_FILE}" "$PYTEST_AUTO_MARK_EXPR"
run_group "fast" 6 "${FAST_GROUP_FILE}" "$PYTEST_AUTO_MARK_EXPR"
