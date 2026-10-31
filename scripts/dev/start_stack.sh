#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/python_contract.sh
source "$ROOT_DIR/scripts/lib/python_contract.sh"
# shellcheck source=../lib/env_contract.sh
source "$ROOT_DIR/scripts/lib/env_contract.sh"
if [[ "${VENOM_STACK_RESOLVED:-0}" != "1" ]]; then
  exec "$(venom_python_bin "$ROOT_DIR")" "$ROOT_DIR/scripts/dev/stack_profile.py" start
fi
cd "$ROOT_DIR"


mk() {
  "${MAKE_BIN:-make}" --no-print-directory "$@"
}

UVICORN="${UVICORN:-.venv/bin/uvicorn}"
API_APP="${API_APP:-venom_core.main:app}"
HOST="${HOST:-0.0.0.0}"
HOST_DISPLAY="${HOST_DISPLAY:-127.0.0.1}"
PORT="${PORT:-8000}"
# Match the selected API listener; a configured dotenv value still overrides this fallback.
export API_PROXY_TARGET="${API_PROXY_TARGET:-http://${HOST_DISPLAY}:${PORT}}"
PID_FILE="${PID_FILE:-.venom.pid}"
WEB_DIR="${WEB_DIR:-web-next}"
WEB_PORT="${WEB_PORT:-3000}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_DISPLAY="${WEB_DISPLAY:-127.0.0.1}"
WEB_PID_FILE="${WEB_PID_FILE:-.web-next.pid}"
START_MODE="${START_MODE:-dev}"
START_WEB_MODE="${START_WEB_MODE:-turbo}"
ALLOW_DEGRADED_START="${ALLOW_DEGRADED_START:-0}"
BACKEND_RELOAD="${BACKEND_RELOAD:-0}"
UVICORN_DEV_FLAGS="${UVICORN_DEV_FLAGS:-}"
UVICORN_PROD_FLAGS="${UVICORN_PROD_FLAGS:---no-server-header}"
BACKEND_LOG="${BACKEND_LOG:-logs/backend.log}"
WEB_LOG="${WEB_LOG:-logs/web-next.log}"
WEB_NODE_PATH="${WEB_NODE_PATH:-}"
WEB_APP_VERSION="${WEB_APP_VERSION:-unknown}"
WEB_START_RETRIES="${WEB_START_RETRIES:-1}"
ENV_FILE_RAW="${ENV_FILE:-.env.dev}"
ENV_EXAMPLE_FILE_RAW="${ENV_EXAMPLE_FILE:-.env.dev.example}"
ENV_FILE="$(env_contract_resolve_file "$ENV_FILE_RAW" "$ROOT_DIR")"
ENV_EXAMPLE_FILE="$(env_contract_resolve_file "$ENV_EXAMPLE_FILE_RAW" "$ROOT_DIR")"
VLLM_ENDPOINT="$(env_contract_get VLLM_ENDPOINT "http://127.0.0.1:8001/v1" "$ENV_FILE")"
OLLAMA_BASE_URL="$(env_contract_get OLLAMA_BASE_URL "http://localhost:11434" "$ENV_FILE")"
OLLAMA_HEALTH_URL="$(env_contract_get OLLAMA_HEALTH_URL "${OLLAMA_BASE_URL%/}/api/tags" "$ENV_FILE")"
VLLM_START_TIMEOUT_SEC="${VLLM_START_TIMEOUT_SEC:-240}"
NPM="${NPM:-npm}"
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  DEFAULT_PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  DEFAULT_PYTHON_BIN="python3"
fi
PYTHON_BIN="${PYTHON_BIN:-$DEFAULT_PYTHON_BIN}"
if [[ "$PYTHON_BIN" != /* ]]; then
  candidate_python="$ROOT_DIR/$PYTHON_BIN"
  if [[ -e "$candidate_python" ]]; then
    PYTHON_BIN="$candidate_python"
  fi
fi

if ! "$PYTHON_BIN" -c "import sys; print(sys.version_info[0])" >/dev/null 2>&1; then
  fallback_python="$(command -v python3 || true)"
  if [[ -n "$fallback_python" ]] && "$fallback_python" -c "import sys; print(sys.version_info[0])" >/dev/null 2>&1; then
    echo "⚠️  PYTHON_BIN='$PYTHON_BIN' jest nieużywalny. Używam fallback: $fallback_python"
    PYTHON_BIN="$fallback_python"
  else
    echo "❌ Nie znaleziono działającego interpretera Python (PYTHON_BIN='$PYTHON_BIN', brak poprawnego python3 w PATH)."
    exit 1
  fi
fi

if ! "$PYTHON_BIN" -c "import dotenv" >/dev/null 2>&1; then
  echo "❌ Brak python-dotenv dla $PYTHON_BIN. Uzupełnij wymagania projektu w wybranym środowisku."
  exit 1
fi

run_with_env_file() {
  # Values such as lifecycle commands remain data; never source a dotenv file.
  "$PYTHON_BIN" -m dotenv -f "$ENV_FILE" run --no-override -- "$@"
}

extract_url_port() {
  local url="$1"
  local scheme="${url%%://*}"
  local rest="${url#*://}"
  rest="${rest%%/*}"
  if [[ "$rest" == *:* ]]; then
    printf '%s' "${rest##*:}"
    return 0
  fi
  if [[ "$scheme" == "https" ]]; then
    printf '443'
  else
    printf '80'
  fi
}

OLLAMA_PORT="$(extract_url_port "$OLLAMA_BASE_URL")"

count_inotify_instances() {
  local total=0
  local proc_fd
  for proc_fd in /proc/[0-9]*/fd; do
    [[ -d "$proc_fd" ]] || continue
    local count
    count="$(ls -l "$proc_fd" 2>/dev/null | grep -c 'anon_inode:inotify' || true)"
    if [[ -n "$count" ]]; then
      total=$((total + count))
    fi
  done
  printf '%s' "$total"
}

inotify_preflight_check() {
  local max_instances
  max_instances="$(cat /proc/sys/fs/inotify/max_user_instances 2>/dev/null || echo "")"
  [[ "$max_instances" =~ ^[0-9]+$ ]] || return 0

  local current_instances
  current_instances="$(count_inotify_instances)"
  [[ "$current_instances" =~ ^[0-9]+$ ]] || return 0

  if (( current_instances >= max_instances )); then
    local running_containers="n/a"
    if command -v docker >/dev/null 2>&1; then
      running_containers="$(docker ps -q 2>/dev/null | wc -l | tr -d '[:space:]')"
    fi
    echo "⚠️  Wysokie zużycie inotify: instances=${current_instances}/${max_instances}."
    echo "⚠️  To może powodować: 'Failed to allocate directory watch: Too many open files'."
    echo "ℹ️  Diagnoza: to zwykle limit instancji inotify (nie klasyczny ulimit -n)."
    echo "ℹ️  running_containers=${running_containers} (jeśli Docker działa)."
    echo "ℹ️  Rekomendacja: podnieś limit, np. 'sysctl -w fs.inotify.max_user_instances=1024'"
    echo "ℹ️  Trwała konfiguracja: /etc/sysctl.d/99-venom-inotify.conf + 'sysctl --system'"
  fi
}

vllm_models_url() {
  local endpoint="$1"
  if [[ "$endpoint" == */v1/models ]]; then
    printf '%s' "$endpoint"
  elif [[ "$endpoint" == */v1 ]]; then
    printf '%s/models' "$endpoint"
  elif [[ "$endpoint" == */v1/ ]]; then
    printf '%smodels' "$endpoint"
  else
    printf '%s/v1/models' "${endpoint%/}"
  fi
}

if [[ ! -x "$UVICORN" ]]; then
  echo "❌ Nie znaleziono uvicorn w $UVICORN. Czy środowisko .venv jest zainstalowane?"
  exit 1
fi

mkdir -p "$(dirname "$BACKEND_LOG")" "$(dirname "$WEB_LOG")" "$(dirname "$PID_FILE")" "$(dirname "$WEB_PID_FILE")"

START_SUCCESS=0
BACKEND_START_RECEIPT=""
UI_TRANSACTION=""

cleanup_partial_start() {
  local original_status=$?
  trap - EXIT INT TERM
  if [[ "$START_SUCCESS" == "1" ]]; then
    return 0
  fi
  local cleanup_status="$original_status"
  if [[ -n "$UI_TRANSACTION" ]]; then
    if ! run_with_env_file node "$ROOT_DIR/web-next/scripts/web-lifecycle.mjs" rollback "$UI_TRANSACTION"; then
      echo "❌ Rollback własnego UI nie został potwierdzony; zachowuję dowody właściciela" >&2
      cleanup_status=1
    fi
  fi
  if [[ -n "$BACKEND_START_RECEIPT" ]]; then
    echo "🧹 Cleanup: zatrzymuję tylko backend z pierwotnej próby startu"
    export ENV_FILE PID_FILE
    if ! "$PYTHON_BIN" -m scripts.dev.startup_rollback "$BACKEND_START_RECEIPT"; then
      echo "❌ Rollback backendu nie został potwierdzony; zachowuję dowody właściciela" >&2
      cleanup_status=1
    fi
  fi
  return "$cleanup_status"
}

trap cleanup_partial_start EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

active_server=""
# Persisted OpenRouter/Vast selection must take precedence over dotenv defaults,
# exactly as it does for API requests. Resolution is offline, never a model call.
active_server="$(run_with_env_file "$PYTHON_BIN" -c 'from venom_core.utils.llm_runtime import get_startup_local_server; print(get_startup_local_server())')"
active_server="$(printf '%s' "$active_server" | tr -d '\r' | tr '[:upper:]' '[:lower:]')"
[[ -z "$active_server" ]] && active_server="ollama"

export VENOM_STARTED_LOCAL_RUNTIME="$active_server"
"$PYTHON_BIN" "$ROOT_DIR/scripts/dev/stack_profile.py" runtime-check

active_server_origin="$(env_contract_origin ACTIVE_LLM_SERVER "$ENV_FILE" "")"
if [[ "$active_server_origin" == "empty" ]]; then
  active_server_origin="default"
fi
vllm_endpoint_origin="$(env_contract_origin VLLM_ENDPOINT "$ENV_FILE" "http://127.0.0.1:8001/v1")"
ollama_health_origin="$(env_contract_origin OLLAMA_HEALTH_URL "$ENV_FILE" "${OLLAMA_BASE_URL%/}/api/tags")"

echo "🧭 Effective config:"
echo "  - ENV_FILE: ${ENV_FILE}"
echo "  - Effective local runtime to start: ${active_server} (persisted selection / settings)"
echo "  - VLLM_ENDPOINT: ${VLLM_ENDPOINT} (${vllm_endpoint_origin})"
echo "  - OLLAMA_HEALTH_URL: ${OLLAMA_HEALTH_URL} (${ollama_health_origin})"
echo "  - START_MODE: ${START_MODE}"
echo "  - START_WEB_MODE: ${START_WEB_MODE}"
echo "  - HOST: ${HOST}:${PORT}, WEB: ${WEB_HOST}:${WEB_PORT}"
inotify_preflight_check

start_ollama() {
  local make_bin
  make_bin="${MAKE_BIN:-make}"
  echo "▶️  Uruchamiam Ollama..."
  if command -v timeout >/dev/null 2>&1; then
    if ! timeout 25s "$make_bin" --no-print-directory ollama-start >/dev/null 2>&1; then
      echo "❌ 'ollama-start' nie zakończył się poprawnie w limicie czasu (25s)."
      return 1
    fi
  else
    if ! "$make_bin" --no-print-directory ollama-start >/dev/null 2>&1; then
      echo "❌ Nie udało się wywołać 'ollama-start' (sprawdź instalację/usługę Ollama)."
      return 1
    fi
  fi

  echo "⏳ Czekam na Ollama (${OLLAMA_HEALTH_URL})..."
  local ollama_fatal=""
  for _ in {1..90}; do
    if curl -fsS "$OLLAMA_HEALTH_URL" >/dev/null 2>&1; then
      echo "✅ Ollama gotowy"
      return 0
    fi
    if [[ -f logs/ollama.log ]] && grep -Eiq "Error: listen tcp .*:${OLLAMA_PORT}|operation not permitted|address already in use" logs/ollama.log; then
      echo "❌ Ollama zakończyła start błędem (sprawdź logs/ollama.log)"
      ollama_fatal="yes"
      break
    fi
    sleep 1
  done
  [[ -z "$ollama_fatal" ]] && echo "❌ Ollama nie wystartowała w czasie (brak odpowiedzi z /api/tags)"
  if [[ -f logs/ollama.log ]]; then
    echo "ℹ️  Ostatnie logi Ollama:"
    tail -n 40 logs/ollama.log || true
  fi
  return 1
}

start_vllm() {
  local models_url
  models_url="$(vllm_models_url "$VLLM_ENDPOINT")"
  echo "▶️  Uruchamiam vLLM..."
  if ! mk vllm-start; then
    echo "❌ Nie udało się uruchomić vLLM (sprawdź logi wyżej)."
    return 1
  fi

  echo "⏳ Czekam na vLLM (/v1/models)..."
  for _ in $(seq 1 "$VLLM_START_TIMEOUT_SEC"); do
    if curl -fsS "$models_url" >/dev/null 2>&1; then
      echo "✅ vLLM gotowy"
      return 0
    fi
    if [[ -f logs/vllm.pid ]]; then
      local vpid
      vpid="$(cat logs/vllm.pid)"
      if ! kill -0 "$vpid" 2>/dev/null; then
        echo "❌ vLLM proces $vpid zakończył się przed gotowością endpointu."
        if [[ -f logs/vllm.log ]]; then
          echo "ℹ️  Ostatnie logi vLLM:"
          tail -n 40 logs/vllm.log || true
        fi
        return 1
      fi
    fi
    sleep 1
  done

  echo "❌ vLLM nie wystartował w czasie (${VLLM_START_TIMEOUT_SEC}s, brak odpowiedzi z /v1/models)"
  if [[ -f logs/vllm.log ]]; then
    echo "ℹ️  Ostatnie logi vLLM:"
    tail -n 40 logs/vllm.log || true
  fi
  return 1
}

start_multi_runtime() {
  local multi_runtime_port
  multi_runtime_port="$(env_contract_get GEMMA4_AUDIO_PORT "8014" "$ENV_FILE")"
  echo "▶️  Uruchamiam Multi-Runtime..."
  if ! bash scripts/llm/multi_runtime_service.sh start; then
    echo "❌ Nie udało się uruchomić Multi-Runtime (sprawdź logi wyżej)."
    return 1
  fi

  echo "⏳ Czekam na Multi-Runtime (/health)..."
  for _ in {1..90}; do
    if curl -fsS "http://127.0.0.1:${multi_runtime_port}/health" >/dev/null 2>&1; then
      echo "✅ Multi-Runtime gotowy"
      return 0
    fi
    sleep 1
  done

  echo "❌ Multi-Runtime nie wystartował w czasie (brak odpowiedzi z /health)"
  if [[ -f logs/multi_runtime_service.log ]]; then
    echo "ℹ️  Ostatnie logi Multi-Runtime:"
    tail -n 40 logs/multi_runtime_service.log || true
  fi
  return 1
}

llm_ready=""
case "$active_server" in
  onnx)
    echo "▶️  Aktywny runtime: ONNX (in-process)"
    llm_ready="onnx"
    ;;
  ollama)
    if start_ollama; then llm_ready="ollama"; fi
    ;;
  vllm)
    if start_vllm; then llm_ready="vllm"; fi
    ;;
  gemma4_audio|multi_runtime)
    if start_multi_runtime; then llm_ready="multi_runtime"; fi
    ;;
  none)
    echo "▶️  ACTIVE_LLM_SERVER=none (start bez lokalnego serwera LLM)"
    llm_ready="none"
    ;;
  *)
    echo "❌ Nieznany ACTIVE_LLM_SERVER='$active_server' (dozwolone: ollama|vllm|multi_runtime|onnx|none)"
    exit 1
    ;;
esac

if [[ -z "$llm_ready" ]]; then
  if [[ "$active_server" == "ollama" && "$START_MODE" == "dev" ]]; then
    echo "⚠️  Ollama niedostępna. Kontynuuję start-dev bez lokalnego LLM (ACTIVE_LLM_SERVER=none)."
    echo "ℹ️  Tryb restrykcyjny bez fallbacku: użyj 'make start-prod ACTIVE_LLM_SERVER=ollama'."
    llm_ready="none"
  elif [[ "$ALLOW_DEGRADED_START" == "1" ]]; then
    echo "⚠️  Tryb degradowany: kontynuuję start bez aktywnego LLM (ALLOW_DEGRADED_START=1)"
    llm_ready="none"
  else
    echo "❌ Nie udało się uruchomić aktywnego LLM: $active_server"
    exit 1
  fi
fi

echo "🧠 LLM gotowy: $llm_ready"

backend_reused=""
if curl -fsS "http://${HOST_DISPLAY}:${PORT}/api/v1/system/status" >/dev/null 2>&1; then
  "$PYTHON_BIN" -c 'import os; from pathlib import Path; from scripts.dev.stack_profile import owned_pid; assert owned_pid(Path.cwd(), os.environ, "PID_FILE", reuse=True), "Unowned API listener"' || exit 1
  echo "Backend wybranego środowiska już działa."
  backend_reused="yes"
fi

if [[ -z "$backend_reused" ]]; then
  if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "⚠️  Venom backend już działa (PID $pid). Użyj 'make stop' lub 'make restart'."
      exit 1
    else
      rm -f "$PID_FILE"
    fi
  fi

  echo "▶️  Uruchamiam Venom backend (uvicorn na ${HOST}:${PORT})"
  : > "$BACKEND_LOG"
  BACKEND_START_RECEIPT="$("$PYTHON_BIN" "$ROOT_DIR/scripts/dev/stack_profile.py" launch-api)"
  echo "✅ Venom backend wystartował z PID $(cat "$PID_FILE")"

  echo "⏳ Czekam na backend (/api/v1/system/status)..."
  backend_ready=""
  for _ in {1..60}; do
    if curl -fsS "http://${HOST_DISPLAY}:${PORT}/api/v1/system/status" >/dev/null 2>&1; then
      backend_ready="yes"
      echo "✅ Backend gotowy"
      break
    fi
    if [[ -f "$PID_FILE" ]]; then
      pid="$(cat "$PID_FILE")"
      if ! kill -0 "$pid" 2>/dev/null; then
        echo "⚠️  Proces startowy backendu $pid nie działa"
        break
      fi
    fi
    sleep 1
  done

  if [[ -z "$backend_ready" ]]; then
    echo "❌ Backend nie wystartował w czasie (brak 200 z /api/v1/system/status)"
    if [[ -f "$BACKEND_LOG" ]]; then
      echo "ℹ️  Ostatnie logi backendu:"
      tail -n 40 "$BACKEND_LOG" || true
    fi
    # EXIT rollback uses the original spawn token and pidfd ownership guard.
    exit 1
  fi
else
  echo "✅ Backend gotowy (używam już działającej instancji)"
fi

# All UI entrypoints share ownership, build compatibility and readiness checks.
export WEB_DIR WEB_PORT WEB_HOST WEB_PID_FILE WEB_LOG NPM
export NODE_PATH="$WEB_NODE_PATH"
export NEXT_PUBLIC_APP_VERSION="$WEB_APP_VERSION"
export NEXT_PUBLIC_ENVIRONMENT_ROLE="${ENVIRONMENT_ROLE:-dev}"
export NEXT_PUBLIC_ENABLE_AUDIO_INTERFACE="$(env_contract_get ENABLE_AUDIO_INTERFACE "false" "$ENV_FILE")"
export NEXT_PUBLIC_AUDIO_WS_BASE="ws://${WEB_DISPLAY}:${PORT}"
export NEXT_TELEMETRY_DISABLED=1
unset NEXT_DISABLE_TURBOPACK WATCHPACK_POLLING WATCHPACK_POLLING_INTERVAL CHOKIDAR_USEPOLLING
# The token exists before launch so rollback also covers interruption after ready.
# A reused UI keeps its earlier token and cannot be claimed by this attempt.
UI_TRANSACTION="$("$PYTHON_BIN" -c 'from uuid import uuid4; print(uuid4())')"
export VENOM_UI_TRANSACTION="$UI_TRANSACTION"


if [[ "$START_MODE" == "prod" ]]; then
  # Building is explicit and invalidates the previous stamp before any attempt.
  run_with_env_file node "$ROOT_DIR/web-next/scripts/web-lifecycle.mjs" build
  run_with_env_file node "$ROOT_DIR/web-next/scripts/web-lifecycle.mjs" start
else
  case "$START_WEB_MODE" in
    turbo|turbo-debug) export WATCHPACK_POLLING=true WATCHPACK_POLLING_INTERVAL=1000 CHOKIDAR_USEPOLLING=1 ;;
    webpack) export NEXT_DISABLE_TURBOPACK=1 ;;
    *) echo "❌ Nieznany START_WEB_MODE=$START_WEB_MODE" >&2; exit 1 ;;
  esac
  run_with_env_file node "$ROOT_DIR/web-next/scripts/web-lifecycle.mjs" dev "$START_WEB_MODE"
fi
# Only a UI with this startup transaction is eligible for failed-start rollback.
echo "🚀 Gotowe: backend http://${HOST_DISPLAY}:${PORT}, dashboard http://${WEB_DISPLAY}:${WEB_PORT}"
START_SUCCESS=1
