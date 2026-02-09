#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/venom
source .venv/bin/activate || true

FAST_GROUP_FILE="config/pytest-groups/fast.txt"
if [[ ! -f "${FAST_GROUP_FILE}" ]]; then
  # Backward compatibility for branches that still use light.txt naming.
  FAST_GROUP_FILE="config/pytest-groups/light.txt"
fi

# Full pytest suite using environment-optimized worker counts (sequential).
echo "▶️  Pytest group: heavy"
pytest -n 1 $(cat config/pytest-groups/heavy.txt)

echo "▶️  Pytest group: long"
pytest -n 2 $(cat config/pytest-groups/long.txt)

echo "▶️  Pytest group: fast"
pytest -n 6 $(cat "${FAST_GROUP_FILE}")
