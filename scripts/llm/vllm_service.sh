#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/env_contract.sh
source "$ROOT_DIR/scripts/lib/env_contract.sh"

VENV_BIN="$ROOT_DIR/.venv/bin"
VLLM_BIN="$VENV_BIN/vllm"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/vllm.pid"
LOG_FILE="$LOG_DIR/vllm.log"
ENV_FILE_RAW="${ENV_FILE:-.env.dev}"
ENV_FILE="$(env_contract_resolve_file "$ENV_FILE_RAW" "$ROOT_DIR")"

MODEL_PATH="$(env_contract_get VLLM_MODEL_PATH "$ROOT_DIR/models/gemma-2b-it" "$ENV_FILE")"
HOST="$(env_contract_get VLLM_HOST "0.0.0.0" "$ENV_FILE")"
PORT="$(env_contract_get VLLM_PORT "8001" "$ENV_FILE")"
GPU_MEMORY_UTILIZATION="$(env_contract_get VLLM_GPU_MEMORY_UTILIZATION "0.85" "$ENV_FILE")"
MAX_BATCHED_TOKENS="$(env_contract_get VLLM_MAX_BATCHED_TOKENS "2048" "$ENV_FILE")"
MAX_MODEL_LEN="$(env_contract_get VLLM_MAX_MODEL_LEN "" "$ENV_FILE")"
MAX_NUM_SEQS="$(env_contract_get VLLM_MAX_NUM_SEQS "" "$ENV_FILE")"
SERVED_MODEL_NAME="$(env_contract_get VLLM_SERVED_MODEL_NAME "" "$ENV_FILE")"
if [[ -z "$SERVED_MODEL_NAME" ]]; then
  SERVED_MODEL_NAME="$(basename "$MODEL_PATH")"
fi
ENFORCE_EAGER="$(env_contract_get VLLM_ENFORCE_EAGER "" "$ENV_FILE")"
CHAT_TEMPLATE="$(env_contract_get VLLM_CHAT_TEMPLATE "" "$ENV_FILE")"

# Wykryj czy używamy systemd
SYSTEMCTL_BIN="$(command -v systemctl || true)"
SYSTEMD_UNIT="$(env_contract_get VLLM_SYSTEMD_UNIT "vllm.service" "$ENV_FILE")"
SYSTEMD_SCOPE="$(env_contract_get VLLM_SYSTEMD_SCOPE "system" "$ENV_FILE")"
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
  echo "🧭 vLLM config: model=${MODEL_PATH}, host=${HOST}, port=${PORT}, env_file=${ENV_FILE}"

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

  if [[ ! -e "$MODEL_PATH" ]]; then
    echo "Brak ścieżki modelu: $MODEL_PATH" >&2
    exit 1
  fi

  if [[ -d "$MODEL_PATH" ]]; then
    if [[ ! -f "$MODEL_PATH/config.json" && ! -f "$MODEL_PATH/params.json" ]] && ! compgen -G "$MODEL_PATH/*.gguf" >/dev/null; then
      echo "Nieprawidłowy katalog modelu vLLM: $MODEL_PATH" >&2
      echo "Wymagane: config.json lub params.json (albo plik *.gguf)." >&2
      exit 1
    fi
  elif [[ -f "$MODEL_PATH" ]]; then
    if [[ "$MODEL_PATH" != *.gguf ]]; then
      echo "Nieprawidłowy plik modelu vLLM: $MODEL_PATH" >&2
      echo "Obsługiwany pojedynczy plik tylko dla GGUF (*.gguf)." >&2
      exit 1
    fi
  else
    echo "Nieprawidłowa ścieżka modelu vLLM: $MODEL_PATH" >&2
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
  if [[ "${ENFORCE_EAGER,,}" == "1" || "${ENFORCE_EAGER,,}" == "true" || "${ENFORCE_EAGER,,}" == "yes" || "${ENFORCE_EAGER,,}" == "on" ]]; then
    cmd+=(--enforce-eager)
  fi
  nohup "${cmd[@]}" >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  local pid
  pid="$(cat "$PID_FILE")"
  # Quick liveness check to fail fast on immediate startup errors.
  sleep 1
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "vLLM zakończył się zaraz po starcie (PID $pid)." >&2
    echo "Ostatnie logi vLLM:" >&2
    tail -n 40 "$LOG_FILE" >&2 || true
    rm -f "$PID_FILE"
    exit 1
  fi
  echo "vLLM start - PID $pid, log: $LOG_FILE"
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
