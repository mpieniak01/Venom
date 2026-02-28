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

# Full pytest suite using environment-optimized worker counts (sequential).
echo "▶️  Pytest group: heavy"
pytest -n 1 $(cat config/pytest-groups/heavy.txt)

echo "▶️  Pytest group: long"
pytest -n 2 $(cat config/pytest-groups/long.txt)

echo "▶️  Pytest group: fast"
pytest -n 6 $(cat "${FAST_GROUP_FILE}")
