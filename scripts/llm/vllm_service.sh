#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
VLLM_BIN="$VENV_BIN/vllm"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/vllm.pid"
LOG_FILE="$LOG_DIR/vllm.log"
ENV_FILE="$ROOT_DIR/.env"
env_get() {
  local key="$1"
  local value="${!key-}"
  if [[ -n "$value" ]]; then
    echo "$value"
    return 0
  fi
  if [[ -f "$ENV_FILE" ]]; then
    awk -F= -v k="$key" '$1 == k {sub(/^[^=]+=*/, "", $0); print $0; exit}' "$ENV_FILE"
  fi
  return 0
}
MODEL_PATH="$(env_get VLLM_MODEL_PATH)"
MODEL_PATH="${MODEL_PATH:-$ROOT_DIR/models/gemma-2b-it}"
HOST="$(env_get VLLM_HOST)"
HOST="${HOST:-0.0.0.0}"
PORT="$(env_get VLLM_PORT)"
PORT="${PORT:-8001}"
GPU_MEMORY_UTILIZATION="$(env_get VLLM_GPU_MEMORY_UTILIZATION)"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.85}"
MAX_BATCHED_TOKENS="$(env_get VLLM_MAX_BATCHED_TOKENS)"
MAX_BATCHED_TOKENS="${MAX_BATCHED_TOKENS:-2048}"
MAX_MODEL_LEN="$(env_get VLLM_MAX_MODEL_LEN)"
MAX_NUM_SEQS="$(env_get VLLM_MAX_NUM_SEQS)"
SERVED_MODEL_NAME="$(env_get VLLM_SERVED_MODEL_NAME)"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-}"
if [[ -z "$SERVED_MODEL_NAME" ]]; then
  SERVED_MODEL_NAME="$(basename "$MODEL_PATH")"
fi
ENFORCE_EAGER="$(env_get VLLM_ENFORCE_EAGER)"
CHAT_TEMPLATE="$(env_get VLLM_CHAT_TEMPLATE)"

# Wykryj czy używamy systemd
SYSTEMCTL_BIN="$(command -v systemctl || true)"
SYSTEMD_UNIT="${VLLM_SYSTEMD_UNIT:-vllm.service}"
SYSTEMD_SCOPE="${VLLM_SYSTEMD_SCOPE:-system}"
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

start() {
  if [[ "$USE_SYSTEMD" == "true" ]]; then
    echo "Uruchamiam usługę systemd ${SYSTEMD_UNIT}"
    "$SYSTEMCTL_BIN" "${SYSTEMD_SCOPE_ARGS[@]}" start "$SYSTEMD_UNIT"
    return 0
  fi

  if [[ ! -x "$VLLM_BIN" ]]; then
    echo "Nie znaleziono binarki vLLM pod $VLLM_BIN" >&2
    exit 1
  fi

  mkdir -p "$LOG_DIR"

  if [[ -f "$PID_FILE" ]]; then
    local existing_pid
    existing_pid="$(cat "$PID_FILE")"
    if kill -0 "$existing_pid" 2>/dev/null; then
      echo "vLLM już działa (PID $existing_pid)"
      exit 0
    else
      rm -f "$PID_FILE"
    fi
  fi

  if [[ ! -d "$MODEL_PATH" ]]; then
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
  if [[ -n "$MAX_MODEL_LEN" ]]; then
    cmd+=(--max-model-len "$MAX_MODEL_LEN")
  fi
  if [[ -n "$MAX_NUM_SEQS" ]]; then
    cmd+=(--max-num-seqs "$MAX_NUM_SEQS")
  fi
  if [[ -n "$SERVED_MODEL_NAME" ]]; then
    cmd+=(--served-model-name "$SERVED_MODEL_NAME")
  fi
  if [[ -n "$CHAT_TEMPLATE" ]]; then
    cmd+=(--chat-template "$CHAT_TEMPLATE")
  fi
  if [[ -n "$ENFORCE_EAGER" ]]; then
    cmd+=(--enforce-eager)
  fi
  nohup "${cmd[@]}" >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  echo "vLLM start - PID $(cat "$PID_FILE"), log: $LOG_FILE"
  return 0
}

stop() {
  if [[ "$USE_SYSTEMD" == "true" ]]; then
    echo "Zatrzymuję usługę systemd ${SYSTEMD_UNIT}"
    "$SYSTEMCTL_BIN" "${SYSTEMD_SCOPE_ARGS[@]}" stop "$SYSTEMD_UNIT"
    return 0
  fi

  if [[ -f "$PID_FILE" ]]; then
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
  return 0
}

restart() {
  stop
  start
  return 0
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
