#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/env_contract.sh
source "$ROOT_DIR/scripts/lib/env_contract.sh"
cd "$ROOT_DIR"

LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/ollama.pid"
LOG_FILE="$LOG_DIR/ollama.log"
ENV_FILE_RAW="${ENV_FILE:-.env.dev}"
ENV_FILE="$(env_contract_resolve_file "$ENV_FILE_RAW" "$ROOT_DIR")"
export ENV_FILE
OLLAMA_BASE_URL="$(env_contract_get OLLAMA_BASE_URL "http://localhost:11434" "$ENV_FILE")"
HEALTH_URL="$(env_contract_get OLLAMA_HEALTH_URL "${OLLAMA_BASE_URL%/}/api/tags" "$ENV_FILE")"
OLLAMA_BIN="$(command -v ollama || true)"
SYSTEMCTL_BIN="$(command -v systemctl || true)"
# An installed unit is not proof that this checkout owns its daemon.
SYSTEMD_UNIT="$(env_contract_get OLLAMA_SYSTEMD_UNIT "" "$ENV_FILE")"
SYSTEMD_SCOPE="$(env_contract_get OLLAMA_SYSTEMD_SCOPE "user" "$ENV_FILE")"
if [[ -n "${PYTHON_BIN:-}" ]]; then
  CONTROL_PYTHON="$PYTHON_BIN"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  CONTROL_PYTHON="$ROOT_DIR/.venv/bin/python"
else
  CONTROL_PYTHON="python3"
fi

runtime_control() {
  "$CONTROL_PYTHON" -m scripts.dev.runtime_teardown "$1"
}

is_healthy() {
  curl -fsS "$HEALTH_URL" >/dev/null 2>&1
}

wait_for_manual_exec() {
  local pid="$1" expected observed attempt
  expected="$(readlink -f "$OLLAMA_BIN")"
  for attempt in {1..100}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "Ollama zakończyła start przed potwierdzeniem właściciela" >&2
      return 1
    fi
    observed="$(readlink -f "/proc/$pid/exe" 2>/dev/null || true)"
    if [[ "$observed" == "$expected" ]]; then
      return 0
    fi
    sleep 0.05
  done
  echo "Nie potwierdzono exec binarnego Ollamy; proces nie został przejęty" >&2
  return 1
}

start() {
  echo "🧭 Ollama config: base_url=${OLLAMA_BASE_URL}, health_url=${HEALTH_URL}, env_file=${ENV_FILE}"
  if is_healthy; then
    runtime_control verify-ollama
    echo "Ollama odpowiada; właściciel runtime potwierdzony"
    return 0
  fi

  if [[ -n "$SYSTEMD_UNIT" ]]; then
    if [[ -z "$SYSTEMCTL_BIN" ]] || [[ ! "$SYSTEMD_UNIT" =~ ^[A-Za-z0-9_][A-Za-z0-9_.@-]*\.service$ ]]; then
      echo "Nieprawidłowa jawna konfiguracja usługi Ollamy" >&2
      return 1
    fi
    local scope_args=()
    case "$SYSTEMD_SCOPE" in
      user) scope_args=(--user) ;;
      system) ;;
      *) echo "Nieprawidłowy OLLAMA_SYSTEMD_SCOPE" >&2; return 1 ;;
    esac
    echo "Uruchamiam skonfigurowaną usługę systemd ${SYSTEMD_UNIT}"
    "$SYSTEMCTL_BIN" "${scope_args[@]}" start -- "$SYSTEMD_UNIT"
    runtime_control verify-ollama
    return 0
  fi

  if [[ -z "$OLLAMA_BIN" ]]; then
    echo "Nie znaleziono polecenia 'ollama' w PATH" >&2
    return 1
  fi
  mkdir -p "$LOG_DIR"
  if [[ -L "$PID_FILE" ]]; then
    echo "Plik PID Ollamy nie może być symlinkiem" >&2
    return 1
  fi
  if [[ -f "$PID_FILE" ]]; then
    local existing_pid
    existing_pid="$(cat "$PID_FILE")"
    if [[ ! "$existing_pid" =~ ^[1-9][0-9]*$ ]] || [[ -d "/proc/$existing_pid" ]]; then
      runtime_control verify-ollama
      echo "Istniejący właściciel procesu Ollamy potwierdzony"
      return 0
    fi
    rm -f "$PID_FILE"
  fi

  echo "Uruchamiam ollama serve (log: $LOG_FILE)"
  nohup "$OLLAMA_BIN" serve >>"$LOG_FILE" 2>&1 &
  local started_pid=$!
  printf '%s\n' "$started_pid" >"$PID_FILE"
  wait_for_manual_exec "$started_pid"
  runtime_control claim-ollama
  echo "Ollama start - PID $started_pid; właściciel zapisany"
}

stop() {
  # The helper verifies PID/start-time/executable/cwd or configured MainPID and
  # drains the owned engine. Never unload or signal a merely reachable daemon.
  runtime_control stop-ollama
}

restart() {
  stop
  start
}

case "$ACTION" in
  start) start ;;
  stop) stop ;;
  restart) restart ;;
  *) echo "Użycie: $0 {start|stop|restart}" >&2; exit 1 ;;
esac
