#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
COMPOSE_FILE="$ROOT_DIR/compose/compose.minimal.yml"

usage() {
  cat <<USAGE
Usage: $(basename "$0") <command>

Commands:
  start      Build and start the minimal Venom stack
  stop       Stop and remove the stack containers
  restart    Restart the stack
  status     Show stack status
  pull       Pull remote images (e.g. Ollama)
USAGE
  return 0
}

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] Docker is not installed or not in PATH." >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "[ERROR] Missing compose file: $COMPOSE_FILE" >&2
  exit 1
fi

cmd=${1:-}
case "$cmd" in
  start)
    docker compose -f "$COMPOSE_FILE" up -d --build
    ;;
  stop)
    docker compose -f "$COMPOSE_FILE" down --remove-orphans
    ;;
  restart)
    docker compose -f "$COMPOSE_FILE" down --remove-orphans
    docker compose -f "$COMPOSE_FILE" up -d --build
    ;;
  status)
    docker compose -f "$COMPOSE_FILE" ps
    ;;
  pull)
    docker compose -f "$COMPOSE_FILE" pull
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
