#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/venom
source .venv/bin/activate || true

# Full pytest suite using environment-optimized worker counts.
pytest -n 1 $(cat config/pytest-groups/heavy.txt)
pytest -n 2 $(cat config/pytest-groups/long.txt)
pytest -n 6 $(cat config/pytest-groups/light.txt)
