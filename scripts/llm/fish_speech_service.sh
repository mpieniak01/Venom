#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/env_contract.sh
source "$ROOT_DIR/scripts/lib/env_contract.sh"

VENV_BIN="$ROOT_DIR/.venv/bin"
PYTHON_BIN="$VENV_BIN/python"
UVICORN_BIN="$VENV_BIN/uvicorn"
RUNTIME_DIR="$ROOT_DIR/.venom_runtime"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$RUNTIME_DIR/fish_speech.pid"
LOG_FILE="$LOG_DIR/fish_speech_service.log"
ENV_FILE_RAW="${ENV_FILE:-.env.dev}"
ENV_FILE="$(env_contract_resolve_file "$ENV_FILE_RAW" "$ROOT_DIR")"

MODEL_ID="$(env_contract_get FISH_SPEECH_MODEL_ID "fishaudio/fish-speech-1.5" "$ENV_FILE")"
HOST="$(env_contract_get FISH_SPEECH_HOST "127.0.0.1" "$ENV_FILE")"
PORT="$(env_contract_get FISH_SPEECH_PORT "8024" "$ENV_FILE")"
CACHE_DIR="$(env_contract_get FISH_SPEECH_CACHE_DIR "models_cache/hf" "$ENV_FILE")"
DEVICE="$(env_contract_get FISH_SPEECH_DEVICE "auto" "$ENV_FILE")"
STARTUP_TIMEOUT_SECONDS="$(env_contract_get FISH_SPEECH_STARTUP_TIMEOUT_SECONDS "600" "$ENV_FILE")"

cleanup_orphan_processes() {
  pkill -TERM -f "uvicorn.*services.fish_speech_runtime.main:app" 2>/dev/null || true
  pkill -TERM -f "services.fish_speech_runtime.main:app" 2>/dev/null || true
  if command -v fuser >/dev/null 2>&1; then
    fuser -k -n tcp "$PORT" >/dev/null 2>&1 || true
  fi
  sleep 1
  pkill -KILL -f "uvicorn.*services.fish_speech_runtime.main:app" 2>/dev/null || true
  pkill -KILL -f "services.fish_speech_runtime.main:app" 2>/dev/null || true
}

health_status() {
  local response
  response="$(curl -fsS "http://${HOST}:${PORT}/health" 2>/dev/null || true)"
  if [[ -z "$response" ]]; then
    echo "unreachable"
    return 1
  fi
  printf '%s' "$response" | "$PYTHON_BIN" -c 'import json,sys; print((json.load(sys.stdin)).get("status","unknown"))'
}

start() {
  mkdir -p "$RUNTIME_DIR" "$LOG_DIR" "$ROOT_DIR/$CACHE_DIR"
  cleanup_orphan_processes
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Fish Speech already running (PID $(cat "$PID_FILE"))"
    return 0
  fi

  export FISH_SPEECH_ENABLED="${FISH_SPEECH_ENABLED:-true}"
  export FISH_SPEECH_MODEL_ID="$MODEL_ID"
  export FISH_SPEECH_HOST="$HOST"
  export FISH_SPEECH_PORT="$PORT"
  export FISH_SPEECH_CACHE_DIR="$ROOT_DIR/$CACHE_DIR"
  export FISH_SPEECH_DEVICE="$DEVICE"
  export FISH_SPEECH_ENDPOINT="http://${HOST}:${PORT}/v1"
  export FISH_SPEECH_LOG_PATH="$LOG_FILE"
  export FISH_SPEECH_PID_PATH="$PID_FILE"
  export PYTHONUNBUFFERED=1

  setsid "$UVICORN_BIN" services.fish_speech_runtime.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level info \
    >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  local pid
  pid="$(cat "$PID_FILE")"

  local waited=0
  while [[ $waited -lt $STARTUP_TIMEOUT_SECONDS ]]; do
    local status
    status="$(health_status || true)"
    if [[ "$status" == "ok" || "$status" == "warming" || "$status" == "disabled" ]]; then
      echo "Fish Speech runtime started (status=${status})"
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "Fish Speech process crashed during startup. Last logs:" >&2
      tail -n 40 "$LOG_FILE" >&2 || true
      rm -f "$PID_FILE"
      return 1
    fi
    sleep 1
    ((waited += 1))
  done
  echo "Fish Speech runtime did not become reachable in ${STARTUP_TIMEOUT_SECONDS}s." >&2
  return 1
}

stop() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    sleep 1
  fi
  cleanup_orphan_processes
  rm -f "$PID_FILE"
  echo "Fish Speech runtime stopped"
}

status() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Fish Speech runtime is running (PID $(cat "$PID_FILE"))"
    echo "Health status: $(health_status || true)"
    return 0
  fi
  echo "Fish Speech runtime is not running"
  return 1
}

health() {
  local status
  status="$(health_status || true)"
  if [[ "$status" == "ok" || "$status" == "warming" || "$status" == "disabled" ]]; then
    echo "Fish Speech runtime health: $status"
    return 0
  fi
  echo "Fish Speech runtime health failed: $status" >&2
  return 1
}

case "$ACTION" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  health) health ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|health}" >&2
    exit 1
    ;;
esac
