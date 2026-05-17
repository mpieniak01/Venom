#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/env_contract.sh
source "$ROOT_DIR/scripts/lib/env_contract.sh"

VENV_BIN="$ROOT_DIR/.venv/bin"
PYTHON_BIN="$VENV_BIN/python"
RUNTIME_DIR="$ROOT_DIR/.venom_runtime"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$RUNTIME_DIR/multi_runtime.pid"
LOG_FILE="$LOG_DIR/multi_runtime_service.log"
ENV_FILE_RAW="${ENV_FILE:-.env.dev}"
ENV_FILE="$(env_contract_resolve_file "$ENV_FILE_RAW" "$ROOT_DIR")"

# Configuration from env
MODEL_ID="$(env_contract_get GEMMA4_AUDIO_MODEL_ID "google/gemma-4-E2B-it" "$ENV_FILE")"
HOST="$(env_contract_get GEMMA4_AUDIO_HOST "127.0.0.1" "$ENV_FILE")"
PORT="$(env_contract_get GEMMA4_AUDIO_PORT "8014" "$ENV_FILE")"
CACHE_DIR="$(env_contract_get GEMMA4_AUDIO_CACHE_DIR "models_cache/hf" "$ENV_FILE")"
DEVICE="$(env_contract_get GEMMA4_AUDIO_DEVICE "auto" "$ENV_FILE")"
MAX_NEW_TOKENS="$(env_contract_get GEMMA4_AUDIO_MAX_NEW_TOKENS "128" "$ENV_FILE")"
STARTUP_TIMEOUT_SECONDS="$(env_contract_get GEMMA4_AUDIO_STARTUP_TIMEOUT_SECONDS "600" "$ENV_FILE")"
PRECISION="$(env_contract_get GEMMA4_AUDIO_PRECISION "int4" "$ENV_FILE")"
QUANT_BACKEND="$(env_contract_get GEMMA4_AUDIO_QUANTIZATION_BACKEND "bitsandbytes" "$ENV_FILE")"
DEVICE_TARGET="$(env_contract_get GEMMA4_AUDIO_DEVICE_TARGET "cuda" "$ENV_FILE")"
CACHE_IMPL="$(env_contract_get GEMMA4_AUDIO_CACHE_IMPLEMENTATION "dynamic" "$ENV_FILE")"
PROBE_ENABLED="$(env_contract_get GEMMA4_AUDIO_PROBE_ENABLED "false" "$ENV_FILE")"
PROBE_TIMEOUT_SECONDS="$(env_contract_get GEMMA4_AUDIO_PROBE_TIMEOUT_SECONDS "20" "$ENV_FILE")"
PROBE_MAX_PROMPT_TOKENS="$(env_contract_get VENOM_INTROSPECTION_PROBE_MAX_PROMPT_TOKENS "$(env_contract_get GEMMA4_AUDIO_PROBE_MAX_PROMPT_TOKENS "1024" "$ENV_FILE")" "$ENV_FILE")"
PROBE_MAX_LAYERS="$(env_contract_get VENOM_INTROSPECTION_PROBE_MAX_LAYER_COUNT "$(env_contract_get VENOM_INTROSPECTION_PROBE_MAX_LAYERS "$(env_contract_get GEMMA4_AUDIO_PROBE_MAX_LAYERS "8" "$ENV_FILE")" "$ENV_FILE")" "$ENV_FILE")"
PROBE_MAX_TOP_K="$(env_contract_get VENOM_INTROSPECTION_PROBE_MAX_TOP_K "$(env_contract_get GEMMA4_AUDIO_PROBE_MAX_TOP_K "32" "$ENV_FILE")" "$ENV_FILE")"
PROBE_HIDDEN_SLICE="$(env_contract_get VENOM_INTROSPECTION_PROBE_MAX_HIDDEN_SLICE "$(env_contract_get GEMMA4_AUDIO_PROBE_HIDDEN_SLICE "16" "$ENV_FILE")" "$ENV_FILE")"

# Detect systemd
SYSTEMCTL_BIN="$(command -v systemctl || true)"
SYSTEMD_UNIT="$(env_contract_get GEMMA4_AUDIO_SYSTEMD_UNIT "gemma4-audio.service" "$ENV_FILE")"
SYSTEMD_SCOPE="$(env_contract_get GEMMA4_AUDIO_SYSTEMD_SCOPE "system" "$ENV_FILE")"
SYSTEMD_SCOPE_ARGS=()
if [[ "$SYSTEMD_SCOPE" == "user" ]]; then
  SYSTEMD_SCOPE_ARGS=(--user)
fi

USE_SYSTEMD=false
if [[ -n "$SYSTEMCTL_BIN" ]] && (
  "$SYSTEMCTL_BIN" "${SYSTEMD_SCOPE_ARGS[@]}" list-unit-files "$SYSTEMD_UNIT" >/dev/null 2>&1 || \
  "$SYSTEMCTL_BIN" "${SYSTEMD_SCOPE_ARGS[@]}" status "$SYSTEMD_UNIT" >/dev/null 2>&1
); then
  USE_SYSTEMD=true
fi

health_status() {
  local response
  response="$(curl -fsS "http://${HOST}:${PORT}/health" 2>/dev/null || true)"
  if [[ -z "$response" ]]; then
    echo "unreachable"
    return 1
  fi

  printf '%s' "$response" | "$PYTHON_BIN" -c 'import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("status", "unknown"))
except Exception:
    print("unknown")'
}

_kill_multi_runtime_strays() {
  local pids pid
  pids="$(pgrep -f "python -m services.multi_runtime.main" || true)"
  for pid in $pids; do
    if [[ "$pid" == "$$" || "$pid" == "$PPID" ]]; then
      continue
    fi
    kill "$pid" 2>/dev/null || true
  done
  sleep 1
  pids="$(pgrep -f "python -m services.multi_runtime.main" || true)"
  for pid in $pids; do
    if [[ "$pid" == "$$" || "$pid" == "$PPID" ]]; then
      continue
    fi
    kill -9 "$pid" 2>/dev/null || true
  done
}

is_ready() {
  [[ "$(health_status)" == "ok" ]]
}

is_warming() {
  [[ "$(health_status)" == "warming" ]]
}

start() {
  echo "🧭 Multi-Runtime config: model=${MODEL_ID}, host=${HOST}, port=${PORT}, device=${DEVICE}, precision=${PRECISION}, quant=${QUANT_BACKEND}, device_target=${DEVICE_TARGET}, env_file=${ENV_FILE}"

  if [[ "$USE_SYSTEMD" == "true" ]]; then
    echo "Starting systemd unit ${SYSTEMD_UNIT}"
    "$SYSTEMCTL_BIN" "${SYSTEMD_SCOPE_ARGS[@]}" start "$SYSTEMD_UNIT"
    return 0
  fi

  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Python binary not found at $PYTHON_BIN" >&2
    exit 1
  fi

  mkdir -p "$RUNTIME_DIR" "$LOG_DIR"

  if [[ -f "$PID_FILE" ]]; then
    local existing_pid
    existing_pid="$(cat "$PID_FILE")"
    if kill -0 "$existing_pid" 2>/dev/null; then
      echo "Multi-Runtime already running (PID $existing_pid)"
      if is_ready; then
        echo "Service is healthy at http://${HOST}:${PORT}/health"
      fi
      exit 0
    else
      rm -f "$PID_FILE"
    fi
  fi

  # Check if model cache directory exists and is accessible
  if [[ ! -d "$ROOT_DIR/$CACHE_DIR" ]]; then
    echo "WARNING: Cache directory does not exist yet: $ROOT_DIR/$CACHE_DIR"
    echo "Model will be downloaded on first startup."
    mkdir -p "$ROOT_DIR/$CACHE_DIR"
  fi

  echo "Starting Multi-Runtime daemon (port ${PORT}, log: $LOG_FILE)"

  # Export environment for the daemon
  export GEMMA4_AUDIO_MODEL_ID="$MODEL_ID"
  export GEMMA4_AUDIO_CACHE_DIR="$ROOT_DIR/$CACHE_DIR"
  export GEMMA4_AUDIO_DEVICE="$DEVICE"
  export GEMMA4_AUDIO_MAX_NEW_TOKENS="$MAX_NEW_TOKENS"
  export GEMMA4_AUDIO_PRECISION="$PRECISION"
  export GEMMA4_AUDIO_QUANTIZATION_BACKEND="$QUANT_BACKEND"
  export GEMMA4_AUDIO_DEVICE_TARGET="$DEVICE_TARGET"
  export GEMMA4_AUDIO_CACHE_IMPLEMENTATION="$CACHE_IMPL"
  export GEMMA4_AUDIO_PROBE_ENABLED="$PROBE_ENABLED"
  export GEMMA4_AUDIO_PROBE_TIMEOUT_SECONDS="$PROBE_TIMEOUT_SECONDS"
  export GEMMA4_AUDIO_PROBE_MAX_PROMPT_TOKENS="$PROBE_MAX_PROMPT_TOKENS"
  export GEMMA4_AUDIO_PROBE_MAX_LAYERS="$PROBE_MAX_LAYERS"
  export GEMMA4_AUDIO_PROBE_MAX_TOP_K="$PROBE_MAX_TOP_K"
  export GEMMA4_AUDIO_PROBE_HIDDEN_SLICE="$PROBE_HIDDEN_SLICE"
  export VENOM_INTROSPECTION_PROBE_MAX_PROMPT_TOKENS="$PROBE_MAX_PROMPT_TOKENS"
  export VENOM_INTROSPECTION_PROBE_MAX_LAYER_COUNT="$PROBE_MAX_LAYERS"
  export VENOM_INTROSPECTION_PROBE_MAX_TOP_K="$PROBE_MAX_TOP_K"
  export VENOM_INTROSPECTION_PROBE_MAX_HIDDEN_SLICE="$PROBE_HIDDEN_SLICE"
  export GEMMA4_AUDIO_HOST="$HOST"
  export GEMMA4_AUDIO_PORT="$PORT"
  export GEMMA4_AUDIO_LOG_PATH="$LOG_FILE"
  export GEMMA4_AUDIO_PID_PATH="$PID_FILE"
  export PYTHONUNBUFFERED=1

  # Start daemon detached from current TTY/session to avoid accidental teardown.
  if command -v setsid >/dev/null 2>&1; then
    setsid "$PYTHON_BIN" -m services.multi_runtime.main </dev/null >>"$LOG_FILE" 2>&1 &
  else
    nohup "$PYTHON_BIN" -m services.multi_runtime.main </dev/null >>"$LOG_FILE" 2>&1 &
  fi
  echo $! >"$PID_FILE"
  local pid
  pid="$(cat "$PID_FILE")"

  # Quick liveness check to fail fast on immediate startup errors
  sleep 2
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "Multi-Runtime crashed immediately after startup (PID $pid)." >&2
    echo "Last logs:" >&2
    tail -n 40 "$LOG_FILE" >&2 || true
    rm -f "$PID_FILE"
    exit 1
  fi

  # Wait for health check (up to configured timeout for model loading)
  local max_wait="$STARTUP_TIMEOUT_SECONDS"
  local waited=0
  echo "Waiting for service health check (up to ${max_wait}s)..."
  while [[ $waited -lt $max_wait ]]; do
    local status
    status="$(health_status)"
    if [[ "$status" == "ok" ]]; then
      echo "Multi-Runtime is healthy!"
      echo "Service started successfully at http://${HOST}:${PORT}"
      echo "Log file: $LOG_FILE"
      echo "PID file: $PID_FILE"
      return 0
    fi

    if [[ "$status" == "error" ]]; then
      echo "Service reported startup error." >&2
      echo "Last logs:" >&2
      tail -n 40 "$LOG_FILE" >&2 || true
      rm -f "$PID_FILE"
      exit 1
    fi

    sleep 2
    ((waited += 2))

    # Check if process is still running
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "Service process died during startup." >&2
      echo "Last logs:" >&2
      tail -n 40 "$LOG_FILE" >&2 || true
      rm -f "$PID_FILE"
      exit 1
    fi

    echo "Service still warming up... (${waited}s elapsed, status=${status})"
  done

  echo "WARNING: Service did not report health after ${max_wait}s."
  echo "Process is running (PID $pid), but health check is not responding."
  echo "Check logs at: $LOG_FILE"
  return 1
}

stop() {
  if [[ "$USE_SYSTEMD" == "true" ]]; then
    echo "Stopping systemd unit ${SYSTEMD_UNIT}"
    "$SYSTEMCTL_BIN" "${SYSTEMD_SCOPE_ARGS[@]}" stop "$SYSTEMD_UNIT" || true
  fi

  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping Multi-Runtime (PID $pid)"
      kill "$pid" 2>/dev/null || true

      # Wait for graceful shutdown (up to 10 seconds)
      local waited=0
      while kill -0 "$pid" 2>/dev/null && [[ $waited -lt 10 ]]; do
        sleep 1
        ((waited += 1))
      done

      # Force kill if still running
      if kill -0 "$pid" 2>/dev/null; then
        echo "Forcing kill of Multi-Runtime (PID $pid)"
        kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$PID_FILE"
  fi

  # Cleanup stray daemon processes with explicit PID filtering.
  _kill_multi_runtime_strays

  echo "Multi-Runtime stopped"
  return 0
}

restart() {
  stop
  sleep 1
  start
  return 0
}

status() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "Multi-Runtime is running (PID $pid)"
      local status
      status="$(health_status)"
      if [[ "$status" == "ok" ]]; then
        echo "Health: OK (http://${HOST}:${PORT}/health)"
      elif [[ "$status" == "warming" ]]; then
        echo "Health: WARMING (http://${HOST}:${PORT}/health)"
      else
        echo "Health: UNKNOWN (health endpoint not responding)"
      fi
      echo "Log: $LOG_FILE"
      echo "Config: model=${MODEL_ID}, host=${HOST}, port=${PORT}"
      return 0
    fi
  fi
  echo "Multi-Runtime is not running"
  return 1
}

health() {
  local status
  status="$(health_status)"
  if [[ "$status" == "ok" ]]; then
    echo "Multi-Runtime is healthy (http://${HOST}:${PORT}/health)"
    return 0
  elif [[ "$status" == "warming" ]]; then
    echo "Multi-Runtime is warming up (http://${HOST}:${PORT}/health)"
    return 2
  else
    echo "Multi-Runtime health check failed (http://${HOST}:${PORT}/health)"
    return 1
  fi
}

show_logs() {
  if [[ -f "$LOG_FILE" ]]; then
    echo "=== Multi-Runtime Service Logs ==="
    tail -n "${1:-50}" "$LOG_FILE"
  else
    echo "No log file found: $LOG_FILE"
  fi
}

usage() {
  echo "Usage: $0 {start|stop|restart|status|health|logs}" >&2
  echo "" >&2
  echo "Commands:" >&2
  echo "  start     - Start the Multi-Runtime daemon" >&2
  echo "  stop      - Stop the daemon" >&2
  echo "  restart   - Restart the daemon" >&2
  echo "  status    - Show daemon status" >&2
  echo "  health    - Check daemon health" >&2
  echo "  logs      - Show recent logs (default: 50 lines)" >&2
}

case "$ACTION" in
  start) start ;;
  stop) stop ;;
  restart) restart ;;
  status) status ;;
  health) health ;;
  logs) show_logs "${2:-50}" ;;
  *)
    usage
    exit 1
    ;;
esac
