#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/env_contract.sh
source "$ROOT_DIR/scripts/lib/env_contract.sh"

CONTROL_PYTHON="$(command -v python3 || true)"
RUNTIME_DIR="$ROOT_DIR/.venom_runtime"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$RUNTIME_DIR/multi_runtime.pid"
LOG_FILE="$LOG_DIR/multi_runtime_service.log"
ENV_FILE_RAW="${ENV_FILE:-.env.dev}"
ENV_FILE="$(env_contract_resolve_file "$ENV_FILE_RAW" "$ROOT_DIR")"
COMPONENTS_DIR="$(env_contract_get VENOM_COMPONENTS_DIR "$ROOT_DIR/.venv-components" "$ENV_FILE")"
PYTHON_BIN="$(env_contract_get MULTI_RUNTIME_COMPONENT_PYTHON "$COMPONENTS_DIR/multi-runtime/bin/python" "$ENV_FILE")"

# Optional explicit paths from env contract. Keep defaults aligned with
# multi_runtime naming, but allow overriding from .env.dev.
PID_FILE_RAW="$(env_contract_get GEMMA4_AUDIO_PID_PATH "$PID_FILE" "$ENV_FILE")"
LOG_FILE_RAW="$(env_contract_get GEMMA4_AUDIO_LOG_PATH "$LOG_FILE" "$ENV_FILE")"
if [[ "$PID_FILE_RAW" = /* ]]; then
  PID_FILE="$PID_FILE_RAW"
else
  PID_FILE="$ROOT_DIR/$PID_FILE_RAW"
fi
if [[ "$LOG_FILE_RAW" = /* ]]; then
  LOG_FILE="$LOG_FILE_RAW"
else
  LOG_FILE="$ROOT_DIR/$LOG_FILE_RAW"
fi
RUNTIME_DIR="$(dirname "$PID_FILE")"
LOG_DIR="$(dirname "$LOG_FILE")"
IDENTITY_FILE="${PID_FILE}.identity.json"

# Configuration from env
MODEL_ID="$(env_contract_get GEMMA4_AUDIO_MODEL_ID "google/gemma-4-E2B-it" "$ENV_FILE")"
HOST="$(env_contract_get GEMMA4_AUDIO_HOST "127.0.0.1" "$ENV_FILE")"
PORT="$(env_contract_get GEMMA4_AUDIO_PORT "8014" "$ENV_FILE")"
CACHE_DIR="$(env_contract_get GEMMA4_AUDIO_CACHE_DIR "models_cache/hf" "$ENV_FILE")"
DEVICE="$(env_contract_get GEMMA4_AUDIO_DEVICE "auto" "$ENV_FILE")"
MAX_NEW_TOKENS="$(env_contract_get GEMMA4_AUDIO_MAX_NEW_TOKENS "128" "$ENV_FILE")"
STARTUP_TIMEOUT_SECONDS="$(env_contract_get GEMMA4_AUDIO_STARTUP_TIMEOUT_SECONDS "600" "$ENV_FILE")"
PRECISION="$(env_contract_get GEMMA4_AUDIO_PRECISION "float16" "$ENV_FILE")"
QUANT_BACKEND="$(env_contract_get GEMMA4_AUDIO_QUANTIZATION_BACKEND "" "$ENV_FILE")"
DEVICE_TARGET="$(env_contract_get GEMMA4_AUDIO_DEVICE_TARGET "cuda" "$ENV_FILE")"
CACHE_IMPL="$(env_contract_get GEMMA4_AUDIO_CACHE_IMPLEMENTATION "dynamic" "$ENV_FILE")"
PROBE_ENABLED="$(env_contract_get GEMMA4_AUDIO_PROBE_ENABLED "false" "$ENV_FILE")"
PROBE_TIMEOUT_SECONDS="$(env_contract_get GEMMA4_AUDIO_PROBE_TIMEOUT_SECONDS "20" "$ENV_FILE")"
PROBE_MAX_PROMPT_TOKENS="$(env_contract_get VENOM_INTROSPECTION_PROBE_MAX_PROMPT_TOKENS "$(env_contract_get GEMMA4_AUDIO_PROBE_MAX_PROMPT_TOKENS "1024" "$ENV_FILE")" "$ENV_FILE")"
PROBE_MAX_LAYERS="$(env_contract_get VENOM_INTROSPECTION_PROBE_MAX_LAYER_COUNT "$(env_contract_get VENOM_INTROSPECTION_PROBE_MAX_LAYERS "$(env_contract_get GEMMA4_AUDIO_PROBE_MAX_LAYERS "8" "$ENV_FILE")" "$ENV_FILE")" "$ENV_FILE")"
PROBE_MAX_TOP_K="$(env_contract_get VENOM_INTROSPECTION_PROBE_MAX_TOP_K "$(env_contract_get GEMMA4_AUDIO_PROBE_MAX_TOP_K "32" "$ENV_FILE")" "$ENV_FILE")"
PROBE_HIDDEN_SLICE="$(env_contract_get VENOM_INTROSPECTION_PROBE_MAX_HIDDEN_SLICE "$(env_contract_get GEMMA4_AUDIO_PROBE_HIDDEN_SLICE "16" "$ENV_FILE")" "$ENV_FILE")"

# Existing GEMMA4_AUDIO_* configuration remains valid; systemd is opt-in.
USE_SYSTEMD="$(env_contract_get MULTI_RUNTIME_USE_SYSTEMD "false" "$ENV_FILE")"
SYSTEMCTL_BIN="$(command -v systemctl || true)"
SYSTEMD_UNIT="$(env_contract_get GEMMA4_AUDIO_SYSTEMD_UNIT "gemma4-audio.service" "$ENV_FILE")"
SYSTEMD_SCOPE="$(env_contract_get GEMMA4_AUDIO_SYSTEMD_SCOPE "system" "$ENV_FILE")"
SYSTEMD_SCOPE_ARGS=()
if [[ "$SYSTEMD_SCOPE" == "user" ]]; then
  SYSTEMD_SCOPE_ARGS=(--user)
fi

component_control() {
  if [[ -z "$CONTROL_PYTHON" ]]; then
    echo "python3 is required for the stdlib-only daemon preflight." >&2
    return 1
  fi
  "$CONTROL_PYTHON" -I "$ROOT_DIR/scripts/llm/component_runtime.py" preflight --python "$PYTHON_BIN" "$@"
}

preflight() {
  if ! component_control; then
    echo "Set MULTI_RUNTIME_COMPONENT_PYTHON to an existing isolated daemon venv interpreter (selected: $PYTHON_BIN). Provision the CUDA component from its qualified lock; the launcher does not install packages." >&2
    return 1
  fi
  case "${USE_SYSTEMD,,}" in
    false|0) return 0 ;;
    true|1) USE_SYSTEMD=true ;;
    *) echo "MULTI_RUNTIME_USE_SYSTEMD must be true or false." >&2; return 1 ;;
  esac
  if [[ -z "$SYSTEMCTL_BIN" || ! "$SYSTEMD_UNIT" =~ ^[[:alnum:]_][[:alnum:]_.@-]*$ ]] || \
     [[ "$SYSTEMD_SCOPE" != "user" && "$SYSTEMD_SCOPE" != "system" ]]; then
    echo "Explicit systemd requires systemctl, a valid unit and system/user scope." >&2
    return 1
  fi
  local description prefix remainder
  description="$("$SYSTEMCTL_BIN" "${SYSTEMD_SCOPE_ARGS[@]}" show --property=ExecStart --value -- "$SYSTEMD_UNIT")" || return 1
  prefix="{ path=$PYTHON_BIN ; argv[]=$PYTHON_BIN -m services.multi_runtime.main ; "
  remainder="${description#"$prefix"}"
  if [[ "$description" != "$prefix"* || "$remainder" != *" }" ]] || \
     [[ "${remainder%??}" == *"{"* || "${remainder%??}" == *"}"* ]]; then
    echo "Systemd ExecStart must directly use $PYTHON_BIN -m services.multi_runtime.main; no unit was changed." >&2
    return 1
  fi
}

read_pid() {
  if [[ -L "$PID_FILE" || -L "$IDENTITY_FILE" ]]; then
    echo "Refusing a symlink daemon PID/identity file." >&2
    return 1
  fi
  local pid
  pid="$(cat "$PID_FILE")" || return 1
  if [[ ! "$pid" =~ ^[0-9]+$ || "$pid" -le 1 ]]; then
    echo "Invalid daemon PID file: $PID_FILE" >&2
    return 1
  fi
  printf '%s' "$pid"
}

owned_pid() {
  component_control --pid "$1" --identity-file "$IDENTITY_FILE"
}

health_status() {
  local response
  response="$(curl -fsS "http://${HOST}:${PORT}/health" 2>/dev/null || true)"
  if [[ -z "$response" ]]; then
    echo "unreachable"
    return 1
  fi

  printf '%s' "$response" | "$CONTROL_PYTHON" -I -c 'import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("status", "unknown"))
except Exception:
    print("unknown")'
}

is_ready() {
  [[ "$(health_status)" == "ok" ]]
}

is_warming() {
  [[ "$(health_status)" == "warming" ]]
}

start() {
  preflight >/dev/null || return 1
  echo "🧭 Multi-Runtime config: model=${MODEL_ID}, host=${HOST}, port=${PORT}, device=${DEVICE}, precision=${PRECISION}, quant=${QUANT_BACKEND}, device_target=${DEVICE_TARGET}, env_file=${ENV_FILE}, python=${PYTHON_BIN}"

  if [[ "$USE_SYSTEMD" == "true" ]]; then
    echo "Starting systemd unit ${SYSTEMD_UNIT}"
    "$SYSTEMCTL_BIN" "${SYSTEMD_SCOPE_ARGS[@]}" start -- "$SYSTEMD_UNIT"
    return 0
  fi

  if [[ -L "$PID_FILE" || -L "$IDENTITY_FILE" || -L "$IDENTITY_FILE.tmp" ]]; then
    echo "Refusing a symlink daemon PID/identity file." >&2
    return 1
  fi
  umask 077
  mkdir -p "$RUNTIME_DIR" "$LOG_DIR"

  if [[ -f "$PID_FILE" || -L "$PID_FILE" ]]; then
    local existing_pid
    existing_pid="$(read_pid)" || return 1
    if kill -0 "$existing_pid" 2>/dev/null; then
      owned_pid "$existing_pid" >/dev/null || return 1
      echo "Multi-Runtime already running (PID $existing_pid)"
      if is_ready; then
        echo "Service is healthy at http://${HOST}:${PORT}/health"
      fi
      return 0
    else
      rm -f "$PID_FILE" "$IDENTITY_FILE"
    fi
  fi

  # A receipt without its PID file cannot own a process.
  rm -f "$IDENTITY_FILE" "$IDENTITY_FILE.tmp"

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

  # Keep model/device flags, but do not inherit application Python hooks/libraries.
  local library_path="/usr/lib/wsl/lib" directory
  for directory in "$(dirname "$(dirname "$PYTHON_BIN")")"/lib/python*/site-packages/nvidia/*/lib; do
    [[ ! -d "$directory" ]] || library_path="$directory:$library_path"
  done
  local detach=(nohup)
  if command -v setsid >/dev/null 2>&1; then
    detach=(setsid)
  fi
  (
    cd "$ROOT_DIR"
    unset PYTHONPATH PYTHONHOME VIRTUAL_ENV LD_PRELOAD
    export LD_LIBRARY_PATH="$library_path"
    export PATH="$(dirname "$PYTHON_BIN"):/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    exec "${detach[@]}" "$PYTHON_BIN" -m services.multi_runtime.main
  ) </dev/null >>"$LOG_FILE" 2>&1 &
  local pid=$!
  printf '%s\n' "$pid" >"$PID_FILE"

  # Quick liveness check to fail fast on immediate startup errors
  sleep 2
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "Multi-Runtime crashed immediately after startup (PID $pid)." >&2
    echo "Last logs:" >&2
    tail -n 40 "$LOG_FILE" >&2 || true
    rm -f "$PID_FILE"
    exit 1
  fi

  # Stamp the real exec identity before trusting readiness or sending signals.
  if ! owned_pid "$pid" >"$IDENTITY_FILE.tmp"; then
    rm -f "$IDENTITY_FILE.tmp"
    return 1
  fi
  mv "$IDENTITY_FILE.tmp" "$IDENTITY_FILE"

  # Wait for health check (up to configured timeout for model loading)
  local max_wait="$STARTUP_TIMEOUT_SECONDS"
  local waited=0
  echo "Waiting for service health check (up to ${max_wait}s)..."
  while [[ $waited -lt $max_wait ]]; do
    local status
    owned_pid "$pid" >/dev/null || return 1
    status="$(health_status || true)"
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
      return 1
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
  preflight >/dev/null || return 1
  if [[ "$USE_SYSTEMD" == "true" ]]; then
    echo "Stopping systemd unit ${SYSTEMD_UNIT}"
    "$SYSTEMCTL_BIN" "${SYSTEMD_SCOPE_ARGS[@]}" stop -- "$SYSTEMD_UNIT"
    return
  fi

  if [[ -f "$PID_FILE" || -L "$PID_FILE" ]]; then
    local pid
    pid="$(read_pid)" || return 1
    if kill -0 "$pid" 2>/dev/null; then
      owned_pid "$pid" >/dev/null || return 1
      echo "Stopping Multi-Runtime (PID $pid)"
      kill "$pid" 2>/dev/null || true
      local waited=0
      while owned_pid "$pid" >/dev/null 2>&1 && [[ $waited -lt 10 ]]; do
        sleep 1
        ((waited += 1))
      done
      # Revalidate immediately before escalation; never signal a reused PID.
      if owned_pid "$pid" >/dev/null 2>&1; then
        echo "Forcing kill of Multi-Runtime (PID $pid)"
        kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$PID_FILE" "$IDENTITY_FILE"
  fi
  echo "Multi-Runtime stopped"
}

restart() {
  preflight >/dev/null || return 1
  stop || return 1
  sleep 1
  start
}

status() {
  if [[ "${USE_SYSTEMD,,}" == "true" || "$USE_SYSTEMD" == "1" ]]; then
    "$SYSTEMCTL_BIN" "${SYSTEMD_SCOPE_ARGS[@]}" status -- "$SYSTEMD_UNIT"
    return
  fi
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(read_pid)" || return 1
    if kill -0 "$pid" 2>/dev/null; then
      owned_pid "$pid" >/dev/null || return 1
      echo "Multi-Runtime is running (PID $pid)"
      local status
      status="$(health_status || true)"
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
  status="$(health_status || true)"
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
  echo "Usage: $0 {start|stop|restart|status|health|logs|preflight}" >&2
  echo "" >&2
  echo "Commands:" >&2
  echo "  preflight - Validate the isolated interpreter without loading models" >&2
  echo "  start     - Start the Multi-Runtime daemon" >&2
  echo "  stop      - Stop the daemon" >&2
  echo "  restart   - Restart the daemon" >&2
  echo "  status    - Show daemon status" >&2
  echo "  health    - Check daemon health" >&2
  echo "  logs      - Show recent logs (default: 50 lines)" >&2
}

case "$ACTION" in
  preflight) preflight ;;
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
