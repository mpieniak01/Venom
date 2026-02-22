#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
COMPOSE_FILE="$ROOT_DIR/compose/compose.release.yml"
COMPOSE_GPU_FILE="$ROOT_DIR/compose/compose.internal.gpu-override.yml"
MODEL_DEFAULT="gemma3:4b"
MODEL="${OLLAMA_MODEL:-$MODEL_DEFAULT}"
GPU_MODE="${VENOM_ENABLE_GPU:-auto}"
RUNTIME_PROFILE="${VENOM_RUNTIME_PROFILE:-light}"
RELEASE_VERSION=""

usage() {
  cat <<USAGE
Usage: $(basename "$0") <command>

Commands:
  start      Pull and start release stack from GHCR
  stop       Stop and remove release stack containers
  restart    Restart release stack
  status     Show release stack status
  pull       Pull release images

Environment:
  VENOM_RUNTIME_PROFILE=light|llm_off|full (default: light)
USAGE
  return 0
}

validate_runtime_profile() {
  case "$RUNTIME_PROFILE" in
    light|llm_off|full) ;;
    *)
      echo "[ERROR] Unsupported VENOM_RUNTIME_PROFILE='$RUNTIME_PROFILE' (expected: light|llm_off|full)." >&2
      exit 1
      ;;
  esac
}

detect_release_version() {
  local version_file="$ROOT_DIR/pyproject.toml"
  if [[ -f "$version_file" ]]; then
    local parsed
    parsed=$(awk -F '"' '/^version = "/ {print $2; exit}' "$version_file")
    if [[ -n "$parsed" ]]; then
      echo "$parsed"
      return 0
    fi
  fi
  echo "1.6.0"
}

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] Docker is not installed or not in PATH." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] Docker Compose plugin ('docker compose') is not available." >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "[ERROR] Missing compose file: $COMPOSE_FILE" >&2
  exit 1
fi

gpu_runtime_available() {
  docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'
  return $?
}

COMPOSE_ARGS=(-f "$COMPOSE_FILE")
enable_gpu=0
case "$GPU_MODE" in
  1|true|on|yes)
    enable_gpu=1
    ;;
  auto)
    if gpu_runtime_available; then
      enable_gpu=1
    fi
    ;;
  0|false|off|no)
    enable_gpu=0
    ;;
  *)
    echo "[WARN] Unknown VENOM_ENABLE_GPU value '$GPU_MODE'. Falling back to auto."
    if gpu_runtime_available; then
      enable_gpu=1
    fi
    ;;
esac

if [[ "$enable_gpu" -eq 1 ]]; then
  if [[ ! -f "$COMPOSE_GPU_FILE" ]]; then
    echo "[ERROR] GPU override file not found: $COMPOSE_GPU_FILE" >&2
    exit 1
  fi
  if gpu_runtime_available; then
    COMPOSE_ARGS+=(-f "$COMPOSE_GPU_FILE")
    echo "[INFO] GPU mode enabled for Ollama."
  else
    echo "[WARN] GPU mode requested, but Docker has no NVIDIA runtime. Falling back to CPU."
  fi
fi

compose_cmd() {
  local active_llm_server="ollama"
  local warmup_on_startup="true"
  local scheme_policy="${URL_SCHEME_POLICY:-force_http}"

  if [[ "$RUNTIME_PROFILE" == "llm_off" ]]; then
    active_llm_server="none"
    warmup_on_startup="false"
  elif [[ "$RUNTIME_PROFILE" == "full" ]]; then
    active_llm_server="${ACTIVE_LLM_SERVER:-ollama}"
  fi

  OLLAMA_MODEL="$MODEL" \
  VENOM_RELEASE_VERSION="$RELEASE_VERSION" \
  URL_SCHEME_POLICY="$scheme_policy" \
  NEXT_PUBLIC_URL_SCHEME_POLICY="${NEXT_PUBLIC_URL_SCHEME_POLICY:-$scheme_policy}" \
  VENOM_RUNTIME_PROFILE="$RUNTIME_PROFILE" \
  ACTIVE_LLM_SERVER="$active_llm_server" \
  LLM_WARMUP_ON_STARTUP="$warmup_on_startup" \
  docker compose "${COMPOSE_ARGS[@]}" "$@"
  return $?
}

compose_up_stack() {
  if [[ "$RUNTIME_PROFILE" == "llm_off" ]]; then
    compose_cmd up -d --no-deps backend frontend
    return $?
  fi
  compose_cmd up -d
  return $?
}

wait_for_ollama() {
  if [[ "$RUNTIME_PROFILE" == "llm_off" ]]; then
    echo "[INFO] Skipping Ollama readiness for profile: llm_off"
    return 0
  fi
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
  if [[ "$RUNTIME_PROFILE" == "llm_off" ]]; then
    echo "[INFO] Skipping model pull for profile: llm_off"
    return 0
  fi
  if compose_cmd exec -T ollama ollama list | awk 'NR>1 {print $1}' | grep -Fxq "$MODEL"; then
    echo "[INFO] Ollama model already present: $MODEL"
    return 0
  fi

  echo "[INFO] Pulling default Ollama model: $MODEL"
  compose_cmd exec -T ollama ollama pull "$MODEL"
  return $?
}

cmd=${1:-}
validate_runtime_profile
RELEASE_VERSION=$(detect_release_version)
case "$cmd" in
  start)
    compose_up_stack
    wait_for_ollama
    ensure_model
    ;;
  stop)
    compose_cmd down --remove-orphans
    ;;
  restart)
    compose_cmd down --remove-orphans
    compose_up_stack
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
