#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/venom
source .venv/bin/activate || true

# Full pytest suite using environment-optimized worker counts (sequential).
echo "▶️  Pytest group: heavy"
pytest -rs -n 1 $(cat config/pytest-groups/heavy.txt)

echo "▶️  Pytest group: long"
pytest -rs -n 2 $(cat config/pytest-groups/long.txt)

echo "▶️  Pytest group: light"
pytest -rs -n 6 $(cat config/pytest-groups/light.txt)
