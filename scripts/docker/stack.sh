#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
COMPOSE_FILE="$ROOT_DIR/compose/compose.minimal.yml"
MODEL_DEFAULT="gemma3:4b"
MODEL="${OLLAMA_MODEL:-$MODEL_DEFAULT}"

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

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] Docker Compose plugin ('docker compose') is not available." >&2
  echo "[HINT] Install a newer Docker version with Compose plugin support." >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "[ERROR] Missing compose file: $COMPOSE_FILE" >&2
  exit 1
fi

compose_cmd() {
  OLLAMA_MODEL="$MODEL" docker compose -f "$COMPOSE_FILE" "$@"
  return $?
}

wait_for_ollama() {
  local timeout=${1:-180}
  local elapsed=0
  local interval=5

  until compose_cmd exec -T ollama ollama list >/dev/null 2>&1; do
    sleep "$interval"
    elapsed=$((elapsed + interval))
    if [[ "$elapsed" -ge "$timeout" ]]; then
      echo "[ERROR] Timeout waiting for Ollama readiness." >&2
      return 1
    fi
  done

  return 0
}

ensure_model() {
  if compose_cmd exec -T ollama ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$MODEL"; then
    echo "[INFO] Ollama model already present: $MODEL"
    return 0
  fi

  echo "[INFO] Pulling default Ollama model: $MODEL"
  compose_cmd exec -T ollama ollama pull "$MODEL"
  return $?
}

cmd=${1:-}
case "$cmd" in
  start)
    compose_cmd up -d --build
    wait_for_ollama
    ensure_model
    ;;
  stop)
    compose_cmd down --remove-orphans
    ;;
  restart)
    compose_cmd down --remove-orphans
    compose_cmd up -d --build
    wait_for_ollama
    ensure_model
    ;;
  status)
    compose_cmd ps
    ;;
  pull)
    compose_cmd pull
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
