#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/ollama.pid"
LOG_FILE="$LOG_DIR/ollama.log"
OLLAMA_BIN="$(command -v ollama || true)"
SYSTEMCTL_BIN="$(command -v systemctl || true)"
SYSTEMD_UNIT="${OLLAMA_SYSTEMD_UNIT:-ollama.service}"
SYSTEMD_SCOPE="${OLLAMA_SYSTEMD_SCOPE:-system}"
SYSTEMD_SCOPE_ARGS=()
if [ "$SYSTEMD_SCOPE" = "user" ]; then
  SYSTEMD_SCOPE_ARGS=(--user)
fi

USE_SYSTEMD=false
if [ -n "$SYSTEMCTL_BIN" ]; then
  if "$SYSTEMCTL_BIN" "${SYSTEMD_SCOPE_ARGS[@]}" list-unit-files "$SYSTEMD_UNIT" >/dev/null 2>&1 || \
     "$SYSTEMCTL_BIN" "${SYSTEMD_SCOPE_ARGS[@]}" status "$SYSTEMD_UNIT" >/dev/null 2>&1; then
    USE_SYSTEMD=true
  fi
fi

start() {
  if [ "$USE_SYSTEMD" = "true" ]; then
    echo "Uruchamiam usługę systemd ${SYSTEMD_UNIT}"
    "$SYSTEMCTL_BIN" "${SYSTEMD_SCOPE_ARGS[@]}" start "$SYSTEMD_UNIT"
    return
  fi

  if [ -z "$OLLAMA_BIN" ]; then
    echo "Nie znaleziono polecenia 'ollama' w PATH" >&2
    exit 1
  fi

  mkdir -p "$LOG_DIR"

  if [ -f "$PID_FILE" ]; then
    local existing_pid
    existing_pid="$(cat "$PID_FILE")"
    if kill -0 "$existing_pid" 2>/dev/null; then
      echo "Ollama już działa (PID $existing_pid)"
      exit 0
    else
      rm -f "$PID_FILE"
    fi
  fi

  echo "Uruchamiam ollama serve (log: $LOG_FILE)"
  nohup "$OLLAMA_BIN" serve >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  echo "Ollama start - PID $(cat "$PID_FILE")"
}

stop() {
  if [ "$USE_SYSTEMD" = "true" ]; then
    echo "Zatrzymuję usługę systemd ${SYSTEMD_UNIT}"
    "$SYSTEMCTL_BIN" "${SYSTEMD_SCOPE_ARGS[@]}" stop "$SYSTEMD_UNIT"
    return
  fi

  if [ -f "$PID_FILE" ]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "Zatrzymuję Ollamę (PID $pid)"
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi

  # Graceful cleanup zombie processes
  pkill -f "ollama serve" 2>/dev/null || true
  echo "Ollama zatrzymana"
}

restart() {
  stop
  start
}

case "$ACTION" in
  start) start ;;
  stop) stop ;;
  restart) restart ;;
  *)
    echo "Użycie: $0 {start|stop|restart}" >&2
    exit 1
    ;;
esac
