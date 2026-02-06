#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
COMPOSE_FILE="$ROOT_DIR/compose/compose.minimal.yml"

usage() {
  cat <<USAGE
Usage: $(basename "$0") <service>

Examples:
  $(basename "$0") backend
  $(basename "$0") frontend
  $(basename "$0") ollama
USAGE
  return 0
}

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] Docker is not installed or not in PATH." >&2
  exit 1
fi

service=${1:-}
if [[ -z "$service" || "$service" == "-h" || "$service" == "--help" ]]; then
  usage
  exit 1
fi

set +e
docker compose -f "$COMPOSE_FILE" exec "$service" /bin/bash
status=$?
set -e

if [[ "$status" -ne 0 ]]; then
  docker compose -f "$COMPOSE_FILE" exec "$service" /bin/sh
fi
