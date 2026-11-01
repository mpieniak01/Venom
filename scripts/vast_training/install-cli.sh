#!/usr/bin/env bash
set -euo pipefail
# Isolated operator tool, never installed into Venom or system Python.
command -v uv >/dev/null || { echo 'Install uv first, or use existing vastai CLI.' >&2; exit 1; }
uv tool install 'vastai==1.10.0'
