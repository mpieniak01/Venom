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

# Full pytest suite using environment-optimized worker counts (sequential).
echo "▶️  Pytest group: heavy"
pytest -n 1 $(read_group_tests "${HEAVY_GROUP_FILE}")

echo "▶️  Pytest group: long"
pytest -n 2 $(read_group_tests "${LONG_GROUP_FILE}")

echo "▶️  Pytest group: fast"
pytest -n 6 $(read_group_tests "${FAST_GROUP_FILE}")
