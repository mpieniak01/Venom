#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
VLLM_BIN="$VENV_BIN/vllm"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/vllm.pid"
LOG_FILE="$LOG_DIR/vllm.log"
MODEL_PATH="${VLLM_MODEL_PATH:-$ROOT_DIR/models/gemma-2b-it}"
HOST="${VLLM_HOST:-0.0.0.0}"
PORT="${VLLM_PORT:-8001}"
GPU_MEMORY_UTILIZATION="${VLLM_GPU_MEMORY_UTILIZATION:-0.85}"
MAX_BATCHED_TOKENS="${VLLM_MAX_BATCHED_TOKENS:-2048}"
SERVED_MODEL_NAME="${VLLM_SERVED_MODEL_NAME:-}"
if [ -z "$SERVED_MODEL_NAME" ]; then
  SERVED_MODEL_NAME="$(basename "$MODEL_PATH")"
fi

# Wykryj czy używamy systemd
SYSTEMCTL_BIN="$(command -v systemctl || true)"
SYSTEMD_UNIT="${VLLM_SYSTEMD_UNIT:-vllm.service}"
SYSTEMD_SCOPE="${VLLM_SYSTEMD_SCOPE:-system}"
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

  if [ ! -x "$VLLM_BIN" ]; then
    echo "Nie znaleziono binarki vLLM pod $VLLM_BIN" >&2
    exit 1
  fi

  mkdir -p "$LOG_DIR"

  if [ -f "$PID_FILE" ]; then
    local existing_pid
    existing_pid="$(cat "$PID_FILE")"
    if kill -0 "$existing_pid" 2>/dev/null; then
      echo "vLLM już działa (PID $existing_pid)"
      exit 0
    else
      rm -f "$PID_FILE"
    fi
  fi

  if [ ! -d "$MODEL_PATH" ]; then
    echo "Brak katalogu modelu: $MODEL_PATH" >&2
    exit 1
  fi

  echo "Uruchamiam vLLM z modelem ${MODEL_PATH} na ${HOST}:${PORT} (gpu_mem=${GPU_MEMORY_UTILIZATION}, max_tokens=${MAX_BATCHED_TOKENS}, served_name=${SERVED_MODEL_NAME})"
  cmd=(
    "$VLLM_BIN" serve "$MODEL_PATH"
    --host "$HOST"
    --port "$PORT"
    --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
    --max-num-batched-tokens "$MAX_BATCHED_TOKENS"
  )
  if [ -n "$SERVED_MODEL_NAME" ]; then
    cmd+=(--served-model-name "$SERVED_MODEL_NAME")
  fi
  nohup "${cmd[@]}" >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  echo "vLLM start - PID $(cat "$PID_FILE"), log: $LOG_FILE"
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
      echo "Zatrzymuję vLLM (PID $pid)"
      kill "$pid" 2>/dev/null || true
      # Graceful shutdown: poczekaj chwilę
      sleep 2
      # Jeśli jeszcze działa, wymuś
      if kill -0 "$pid" 2>/dev/null; then
        echo "Wymuszam zatrzymanie vLLM (SIGKILL)"
        kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$PID_FILE"
  fi

  # Cleanup zombie processes
  pkill -9 -f "vllm serve" 2>/dev/null || true
  echo "vLLM zatrzymany"
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
