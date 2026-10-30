#!/usr/bin/env bash
# Resolve the project interpreter before delegating to Python.
venom_python_bin() {
  local root_dir="$1"
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    printf '%s' "$PYTHON_BIN"
  elif [[ -x "$root_dir/.venv/bin/python" ]]; then
    printf '%s' "$root_dir/.venv/bin/python"
  else
    command -v python3
  fi
}
