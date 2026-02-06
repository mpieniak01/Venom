#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
COMPOSE_FILE="$ROOT_DIR/compose/compose.minimal.yml"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [service ...]

Examples:
  $(basename "$0")
  $(basename "$0") backend
  $(basename "$0") backend frontend
USAGE
}

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] Docker is not installed or not in PATH." >&2
  exit 1
fi

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

if [ "$#" -eq 0 ]; then
  docker compose -f "$COMPOSE_FILE" logs -f --tail 200
else
  docker compose -f "$COMPOSE_FILE" logs -f --tail 200 "$@"
fi
