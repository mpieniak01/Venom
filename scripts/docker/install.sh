#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
COMPOSE_FILE="$ROOT_DIR/compose/compose.minimal.yml"
MODEL_DEFAULT="gemma3:4b"
MODEL="$MODEL_DEFAULT"
OLLAMA_IMAGE_DEFAULT="ollama/ollama:latest"
OLLAMA_IMAGE="$OLLAMA_IMAGE_DEFAULT"
QUICK=0
SKIP_MODEL_PULL=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --quick             Run with defaults (no prompts)
  --model <name>      Ollama model to pull (default: ${MODEL_DEFAULT})
  --ollama-image <i>  Ollama image tag (default: ${OLLAMA_IMAGE_DEFAULT})
  --skip-model-pull   Do not pull model during install
  -h, --help          Show this help
USAGE
  return 0
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --quick)
      QUICK=1
      ;;
    --model)
      shift
      MODEL=${1:-}
      if [[ -z "$MODEL" ]]; then
        echo "[ERROR] --model requires a value." >&2
        exit 1
      fi
      ;;
    --ollama-image)
      shift
      OLLAMA_IMAGE=${1:-}
      if [[ -z "$OLLAMA_IMAGE" ]]; then
        echo "[ERROR] --ollama-image requires a value." >&2
        exit 1
      fi
      ;;
    --skip-model-pull)
      SKIP_MODEL_PULL=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

step=0
steps_total=7
if [[ "$SKIP_MODEL_PULL" -eq 1 ]]; then
  steps_total=6
fi

print_step() {
  local message=${1:-}
  step=$((step + 1))
  echo
  echo "[$step/$steps_total] $message"
  return 0
}

require_cmd() {
  local cmd_name=${1:-}
  if [[ -z "$cmd_name" ]]; then
    echo "[ERROR] Missing command name in require_cmd." >&2
    return 1
  fi
  if ! command -v "$cmd_name" >/dev/null 2>&1; then
    echo "[ERROR] Missing required command: $cmd_name" >&2
    exit 1
  fi
  return 0
}

wait_http() {
  local url=${1:-}
  local timeout=${2:-180}
  local elapsed=0
  local interval=5

  if [[ -z "$url" ]]; then
    echo "[ERROR] wait_http requires URL argument." >&2
    return 1
  fi

  until curl -fsS "$url" >/dev/null 2>&1; do
    sleep "$interval"
    elapsed=$((elapsed + interval))
    echo "  ... waiting for $url (${elapsed}s/${timeout}s)"
    if [[ "$elapsed" -ge "$timeout" ]]; then
      echo "[ERROR] Timeout waiting for $url" >&2
      return 1
    fi
  done

  echo "  OK: $url"
  return 0
}

print_disk_hint() {
  local avail_gb
  avail_gb=$(df -Pk "$ROOT_DIR" | awk 'NR==2 {print int($4/1024/1024)}')
  echo "[INFO] Estimated download: ~5.5-9.5 GB"
  echo "[INFO] Estimated post-install size: ~7-13 GB"
  echo "[INFO] Recommended free disk: >=20 GB (safe: 25 GB)"
  echo "[INFO] Detected free disk near repo: ${avail_gb} GB"
  if [[ "$avail_gb" -lt 20 ]]; then
    echo "[WARN] Free disk below 20 GB. Installation may fail."
  fi
  return 0
}

if [[ "$QUICK" -eq 0 && "$SKIP_MODEL_PULL" -eq 0 ]]; then
  read -r -p "Pull model '$MODEL' during install? [Y/n]: " ans
  ans=${ans:-Y}
  case "$ans" in
    [Nn]*) SKIP_MODEL_PULL=1; steps_total=6 ;;
    *) ;;
  esac
fi

print_step "Checking environment"
require_cmd docker
require_cmd curl
if ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] docker compose plugin is required." >&2
  exit 1
fi
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "[ERROR] Missing compose file: $COMPOSE_FILE" >&2
  exit 1
fi
print_disk_hint

print_step "Pulling remote images (Ollama and base layers)"
OLLAMA_IMAGE="$OLLAMA_IMAGE" docker compose -f "$COMPOSE_FILE" pull

print_step "Building Venom images (backend + frontend)"
OLLAMA_IMAGE="$OLLAMA_IMAGE" docker compose -f "$COMPOSE_FILE" build backend frontend

print_step "Starting minimal stack"
OLLAMA_IMAGE="$OLLAMA_IMAGE" docker compose -f "$COMPOSE_FILE" up -d

print_step "Waiting for health checks"
wait_http "http://127.0.0.1:11434/api/tags" 180
wait_http "http://127.0.0.1:8000/api/v1/system/status" 240
wait_http "http://127.0.0.1:3000" 240

if [[ "$SKIP_MODEL_PULL" -eq 0 ]]; then
  print_step "Pulling Ollama model: $MODEL"
  OLLAMA_IMAGE="$OLLAMA_IMAGE" docker compose -f "$COMPOSE_FILE" exec -T ollama ollama pull "$MODEL"
fi

print_step "Done"
echo "[OK] Venom minimal stack is ready."
echo "[INFO] UI:      http://127.0.0.1:3000"
echo "[INFO] Backend: http://127.0.0.1:8000"
echo "[INFO] Logs:    scripts/docker/logs.sh"
echo "[INFO] Stop:    scripts/docker/stack.sh stop"
