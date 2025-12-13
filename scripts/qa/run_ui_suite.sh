#!/usr/bin/env bash

# Venom – prosty wrapper do uruchamiania smoke-testów backendu.
# 1. Zakłada (jeśli trzeba) środowisko .venv
# 2. Instaluję minimalny zestaw zależności do uruchomienia pytest
# 3. Uruchamia pełny zestaw testów (można go zawęzić zmienną PYTEST_ARGS)

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"
PYTEST_ARGS="${PYTEST_ARGS:-}"

if [ ! -d "${VENV_DIR}" ]; then
  echo "🧪 Tworzę środowisko virtualenv w ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"

echo "⬆️  Aktualizuję pip + instaluję pytest (pozostałe zależności wg potrzeby)"
pip install --upgrade pip >/dev/null
pip install pytest >/dev/null

echo "▶️  Uruchamiam pytest ${PYTEST_ARGS:-'(pełna ścieżka tests/)'}"
if [ -n "${PYTEST_ARGS}" ]; then
  pytest ${PYTEST_ARGS}
else
  pytest -q
fi
