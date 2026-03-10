#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/env_contract.sh
source "$ROOT_DIR/scripts/lib/env_contract.sh"

mk() {
  "${MAKE_BIN:-make}" --no-print-directory "$@"
}

UVICORN="${UVICORN:-.venv/bin/uvicorn}"
API_APP="${API_APP:-venom_core.main:app}"
HOST="${HOST:-0.0.0.0}"
HOST_DISPLAY="${HOST_DISPLAY:-127.0.0.1}"
PORT="${PORT:-8000}"
PID_FILE="${PID_FILE:-.venom.pid}"
WEB_DIR="${WEB_DIR:-web-next}"
WEB_PORT="${WEB_PORT:-3000}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_DISPLAY="${WEB_DISPLAY:-127.0.0.1}"
WEB_PID_FILE="${WEB_PID_FILE:-.web-next.pid}"
START_MODE="${START_MODE:-dev}"
START_WEB_MODE="${START_WEB_MODE:-webpack}"
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
PYTHON_BIN="${PYTHON_BIN:-python3}"
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

DOTENV_AVAILABLE="0"
if "$PYTHON_BIN" -c "import dotenv" >/dev/null 2>&1; then
  DOTENV_AVAILABLE="1"
else
  echo "⚠️  Brak modułu 'python-dotenv' dla $PYTHON_BIN. Używam fallback: source '$ENV_FILE'."
fi

run_with_env_file() {
  if [[ "$DOTENV_AVAILABLE" == "1" ]]; then
    "$PYTHON_BIN" -m dotenv -f "$ENV_FILE" run -- "$@"
  else
    (
      set -a
      # shellcheck disable=SC1090
      source "$ENV_FILE"
      set +a
      "$@"
    )
  fi
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

mkdir -p logs

START_SUCCESS=0
BACKEND_STARTED=0
UI_STARTED=0

kill_pid_group_graceful() {
  local pid="${1:-}"
  local label="${2:-process}"
  if [[ -z "$pid" ]]; then
    return 0
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    return 0
  fi
  kill -TERM -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
  for _ in {1..20}; do
    if kill -0 "$pid" 2>/dev/null; then
      sleep 0.2
    else
      return 0
    fi
  done
  echo "⚠️  Wymuszam kill -9 dla ${label} (PID ${pid})"
  kill -KILL -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
}

cleanup_partial_start() {
  if [[ "$START_SUCCESS" == "1" ]]; then
    return 0
  fi
  if [[ "$UI_STARTED" == "1" && -f "$WEB_PID_FILE" ]]; then
    local wpid
    wpid="$(cat "$WEB_PID_FILE" 2>/dev/null || true)"
    if [[ -n "$wpid" ]]; then
      echo "🧹 Cleanup: zatrzymuję częściowo uruchomiony UI (PID ${wpid})"
      kill_pid_group_graceful "$wpid" "UI"
    fi
    rm -f "$WEB_PID_FILE"
  fi
  if [[ "$BACKEND_STARTED" == "1" && -f "$PID_FILE" ]]; then
    local bpid
    bpid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$bpid" ]]; then
      echo "🧹 Cleanup: zatrzymuję częściowo uruchomiony backend (PID ${bpid})"
      kill_pid_group_graceful "$bpid" "backend"
    fi
    rm -f "$PID_FILE"
  fi
}

trap cleanup_partial_start EXIT INT TERM

active_server=""
active_server="$(env_contract_get ACTIVE_LLM_SERVER "" "$ENV_FILE")"
active_server="$(printf '%s' "$active_server" | tr -d '\r' | tr '[:upper:]' '[:lower:]')"
[[ -z "$active_server" ]] && active_server="ollama"

active_server_origin="$(env_contract_origin ACTIVE_LLM_SERVER "$ENV_FILE" "")"
if [[ "$active_server_origin" == "empty" ]]; then
  active_server_origin="default"
fi
vllm_endpoint_origin="$(env_contract_origin VLLM_ENDPOINT "$ENV_FILE" "http://127.0.0.1:8001/v1")"
ollama_health_origin="$(env_contract_origin OLLAMA_HEALTH_URL "$ENV_FILE" "${OLLAMA_BASE_URL%/}/api/tags")"

echo "🧭 Effective config:"
echo "  - ENV_FILE: ${ENV_FILE}"
echo "  - ACTIVE_LLM_SERVER: ${active_server} (${active_server_origin})"
echo "  - VLLM_ENDPOINT: ${VLLM_ENDPOINT} (${vllm_endpoint_origin})"
echo "  - OLLAMA_HEALTH_URL: ${OLLAMA_HEALTH_URL} (${ollama_health_origin})"
echo "  - START_MODE: ${START_MODE}"
echo "  - START_WEB_MODE: ${START_WEB_MODE}"
echo "  - HOST: ${HOST}:${PORT}, WEB: ${WEB_HOST}:${WEB_PORT}"

start_ollama() {
  local make_bin
  make_bin="${MAKE_BIN:-make}"
  echo "▶️  Uruchamiam Ollama..."
  mk vllm-stop >/dev/null || true
  if command -v timeout >/dev/null 2>&1; then
    if ! timeout 25s "$make_bin" --no-print-directory ollama-start >/dev/null; then
      echo "❌ 'ollama-start' nie zakończył się poprawnie w limicie czasu (25s)."
      return 1
    fi
  else
    if ! "$make_bin" --no-print-directory ollama-start >/dev/null; then
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
  mk ollama-stop >/dev/null || true
  return 1
}

start_vllm() {
  local models_url
  models_url="$(vllm_models_url "$VLLM_ENDPOINT")"
  echo "▶️  Uruchamiam vLLM..."
  mk ollama-stop >/dev/null || true
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
  mk vllm-stop >/dev/null || true
  return 1
}

llm_ready=""
case "$active_server" in
  onnx)
    echo "▶️  Aktywny runtime: ONNX (in-process)"
    mk vllm-stop >/dev/null || true
    mk ollama-stop >/dev/null || true
    llm_ready="onnx"
    ;;
  ollama)
    mk vllm-stop >/dev/null || true
    if start_ollama; then llm_ready="ollama"; fi
    ;;
  vllm)
    mk ollama-stop >/dev/null || true
    if start_vllm; then llm_ready="vllm"; fi
    ;;
  none)
    echo "▶️  ACTIVE_LLM_SERVER=none (start bez lokalnego serwera LLM)"
    mk vllm-stop >/dev/null || true
    mk ollama-stop >/dev/null || true
    llm_ready="none"
    ;;
  *)
    echo "❌ Nieznany ACTIVE_LLM_SERVER='$active_server' (dozwolone: ollama|vllm|onnx|none)"
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
  echo "⚠️  Backend już odpowiada na ${HOST_DISPLAY}:${PORT}. Pomijam drugi start backendu."
  backend_reused="yes"
  if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE")"
    if ! kill -0 "$pid" 2>/dev/null; then rm -f "$PID_FILE"; fi
  fi
elif [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "⚠️  Backend PID $pid istnieje, ale /system/status jest niedostępny. Restartuję backend."
    kill "$pid" 2>/dev/null || true
    for _ in {1..30}; do
      if kill -0 "$pid" 2>/dev/null; then sleep 0.2; else break; fi
    done
    rm -f "$PID_FILE"
  else
    rm -f "$PID_FILE"
  fi
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

  if [[ "$START_MODE" == "prod" ]]; then
    uvicorn_flags="--host ${HOST} --port ${PORT} ${UVICORN_PROD_FLAGS}"
  else
    if [[ "$BACKEND_RELOAD" == "1" ]]; then
      uvicorn_flags="--host ${HOST} --port ${PORT} ${UVICORN_DEV_FLAGS}"
      echo "ℹ️  Backend dev z autoreload (BACKEND_RELOAD=1)"
    else
      uvicorn_flags="--host ${HOST} --port ${PORT} ${UVICORN_PROD_FLAGS}"
      echo "ℹ️  Backend dev w trybie stabilnym bez autoreload (BACKEND_RELOAD=0)"
    fi
  fi

  echo "▶️  Uruchamiam Venom backend (uvicorn na ${HOST}:${PORT})"
  : > "$BACKEND_LOG"
  run_with_env_file setsid "$UVICORN" "$API_APP" $uvicorn_flags >> "$BACKEND_LOG" 2>&1 &
  echo $! > "$PID_FILE"
  BACKEND_STARTED=1
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
    if [[ -f "$PID_FILE" ]]; then
      bpid="$(cat "$PID_FILE")"
      kill "$bpid" 2>/dev/null || true
      rm -f "$PID_FILE"
      BACKEND_STARTED=0
    fi
    mk vllm-stop >/dev/null || true
    mk ollama-stop >/dev/null || true
    exit 1
  fi
else
  echo "✅ Backend gotowy (używam już działającej instancji)"
fi

ui_skip=""
if [[ ! -f "$WEB_PID_FILE" ]]; then
  ext_ui_pids="$(bash scripts/dev/port_pids.sh "$WEB_PORT" || true)"
  if [[ -n "$ext_ui_pids" ]]; then
    echo "⚠️  Port ${WEB_PORT} zajęty przez niezarządzany proces UI ($ext_ui_pids). Czyszczę."
    kill $ext_ui_pids 2>/dev/null || true
    for _ in {1..30}; do
      ext_still="$(bash scripts/dev/port_pids.sh "$WEB_PORT" || true)"
      [[ -z "$ext_still" ]] && break
      sleep 0.2
    done
    ext_still="$(bash scripts/dev/port_pids.sh "$WEB_PORT" || true)"
    if [[ -n "$ext_still" ]]; then
      echo "❌ Nie udało się zwolnić portu ${WEB_PORT} (PID: $ext_still). Użyj: make web-stop"
      exit 1
    fi
  fi
fi

if [[ -f "$WEB_PID_FILE" ]]; then
  wpid="$(cat "$WEB_PID_FILE")"
  if kill -0 "$wpid" 2>/dev/null; then
    if [[ "$START_MODE" == "dev" ]]; then
      cmdline="$(tr '\0' ' ' < /proc/${wpid}/cmdline 2>/dev/null || true)"
      want="dev --"
      if [[ "$START_WEB_MODE" == "turbo" ]]; then
        want="dev:turbo"
      elif [[ "$START_WEB_MODE" == "turbo-debug" ]]; then
        want="dev:turbo:debug"
      fi
      if printf '%s' "$cmdline" | grep -Fq "$want"; then
        echo "⚠️  UI (Next.js) już działa w trybie ${START_WEB_MODE} (PID ${wpid}). Pomijam start UI."
        ui_skip="yes"
      else
        echo "🔁 UI (Next.js) działa w innym trybie. Restartuję do trybu ${START_WEB_MODE}."
        kill -TERM -"$wpid" 2>/dev/null || kill "$wpid" 2>/dev/null || true
        for _ in {1..20}; do
          if kill -0 "$wpid" 2>/dev/null; then sleep 0.2; else break; fi
        done
        if kill -0 "$wpid" 2>/dev/null; then
          kill -KILL -"$wpid" 2>/dev/null || kill -KILL "$wpid" 2>/dev/null || true
        fi
        rm -f "$WEB_PID_FILE"
      fi
    else
      echo "⚠️  UI (Next.js) już działa (PID ${wpid}). Pomijam start UI."
      ui_skip="yes"
    fi
  else
    rm -f "$WEB_PID_FILE"
  fi
fi

if [[ -z "$ui_skip" ]]; then
  start_ui_process() {
    local mode="$1"
    local npm_command="dev"
    case "$mode" in
      prod)
        npm_command="start"
        ;;
      turbo)
        npm_command="dev:turbo"
        ;;
      turbo-debug)
        npm_command="dev:turbo:debug"
        ;;
      webpack)
        npm_command="dev"
        ;;
      *)
        echo "❌ Nieznany tryb uruchomienia UI: ${mode}" >&2
        return 1
        ;;
    esac

    (
      cd "$WEB_DIR"
      export NODE_PATH="$WEB_NODE_PATH"
      export NEXT_PUBLIC_APP_VERSION="$WEB_APP_VERSION"
      export NEXT_PUBLIC_ENVIRONMENT_ROLE="${ENVIRONMENT_ROLE:-dev}"
      export NEXT_TELEMETRY_DISABLED=1
      unset NEXT_DISABLE_TURBOPACK WATCHPACK_POLLING WATCHPACK_POLLING_INTERVAL CHOKIDAR_USEPOLLING

      if [[ "$mode" == "prod" ]]; then
        export NEXT_MODE=prod
      elif [[ "$mode" == "webpack" ]]; then
        export NEXT_MODE=dev
        export NEXT_DISABLE_TURBOPACK=1
      else
        export NEXT_MODE=dev
        export WATCHPACK_POLLING=true
        export WATCHPACK_POLLING_INTERVAL=1000
        export CHOKIDAR_USEPOLLING=1
      fi

      run_with_env_file setsid "$NPM" run "$npm_command" -- --hostname "$WEB_HOST" --port "$WEB_PORT" >> "../$WEB_LOG" 2>&1 &
      echo $! > "../$WEB_PID_FILE"
    )
  }

  wait_for_ui_ready() {
    local pid="$1"
    local failure_label="$2"
    local ready=""
    for _ in {1..40}; do
      if kill -0 "$pid" 2>/dev/null; then
        if curl -fsS "http://${WEB_DISPLAY}:${WEB_PORT}" >/dev/null 2>&1; then
          ready="yes"
          break
        fi
      else
        echo "$failure_label proces $pid zakończył się przed startem" >&2
        break
      fi
      sleep 1
    done
    printf '%s' "$ready"
  }

  : > "$WEB_LOG"
  if [[ "$START_MODE" == "prod" ]]; then
    echo "🛠  Buduję Next.js (npm run build)"
    if ! (
      cd "$WEB_DIR"
      NODE_PATH="$WEB_NODE_PATH" NEXT_PUBLIC_APP_VERSION="$WEB_APP_VERSION" NEXT_PUBLIC_ENVIRONMENT_ROLE="${ENVIRONMENT_ROLE:-dev}" NEXT_MODE=prod NEXT_TELEMETRY_DISABLED=1 "$NPM" run build >/dev/null 2>&1
    ); then
      echo "❌ Build UI (Next.js) nie powiódł się (tryb prod)." >&2
      if [[ -f "$PID_FILE" ]]; then
        bpid="$(cat "$PID_FILE")"
        kill "$bpid" 2>/dev/null || true
        rm -f "$PID_FILE"
      fi
      mk vllm-stop >/dev/null || true
      mk ollama-stop >/dev/null || true
      exit 1
    fi
    echo "▶️  Uruchamiam UI (Next.js start, host ${WEB_HOST}, port ${WEB_PORT})"
    start_ui_process "prod"
  else
    if [[ "$START_WEB_MODE" != "webpack" && "$START_WEB_MODE" != "turbo" && "$START_WEB_MODE" != "turbo-debug" ]]; then
      echo "❌ Nieznany START_WEB_MODE='${START_WEB_MODE}' (dozwolone: webpack|turbo|turbo-debug)"
      exit 1
    fi
    if [[ "$START_WEB_MODE" == "turbo" ]]; then
      echo "▶️  Uruchamiam UI (Next.js dev:turbo, host ${WEB_HOST}, port ${WEB_PORT})"
      start_ui_process "turbo"
    elif [[ "$START_WEB_MODE" == "turbo-debug" ]]; then
      echo "▶️  Uruchamiam UI (Next.js dev:turbo:debug, host ${WEB_HOST}, port ${WEB_PORT})"
      start_ui_process "turbo-debug"
    else
      echo "▶️  Uruchamiam UI (Next.js dev, host ${WEB_HOST}, port ${WEB_PORT})"
      start_ui_process "webpack"
    fi
  fi

  effective_web_mode="$START_WEB_MODE"
  ui_ready=""
  max_attempts=$((WEB_START_RETRIES + 1))
  for attempt in $(seq 1 "$max_attempts"); do
    wpid="$(cat "$WEB_PID_FILE")"
    UI_STARTED=1
    ui_ready="$(wait_for_ui_ready "$wpid" "❌ UI (Next.js)")"
    if [[ -n "$ui_ready" ]]; then
      break
    fi

    echo "⚠️  UI (Next.js) nie wystartował poprawnie (próba ${attempt}/${max_attempts})."
    kill_pid_group_graceful "$wpid" "UI"
    rm -f "$WEB_PID_FILE"
    UI_STARTED=0

    should_retry_same_mode=0
    if [[ "$attempt" -lt "$max_attempts" ]]; then
      should_retry_same_mode=1
    fi

    if [[ "$START_MODE" == "dev" ]] && { [[ "$effective_web_mode" == "turbo" ]] || [[ "$effective_web_mode" == "turbo-debug" ]]; } && [[ -f "$WEB_LOG" ]] && grep -Eiq "Too many open files|Failed to allocate directory watch" "$WEB_LOG"; then
      echo "⚠️  Turbopack nie wystartował przez błąd watchera. Przełączam UI na fallback webpack."
      : > "$WEB_LOG"
      start_ui_process "webpack"
      effective_web_mode="webpack"
      continue
    fi

    if [[ "$should_retry_same_mode" -eq 1 ]]; then
      echo "🔁 Ponawiam start UI w tym samym trybie (${effective_web_mode})."
      : > "$WEB_LOG"
      start_ui_process "$effective_web_mode"
      continue
    fi
  done

  if [[ -z "$ui_ready" ]]; then
    mk vllm-stop >/dev/null || true
    mk ollama-stop >/dev/null || true
    exit 1
  fi

  if [[ "$START_MODE" == "dev" ]]; then
    expected_bundler="turbopack"
    [[ "$effective_web_mode" == "webpack" ]] && expected_bundler="webpack"
    bundler_line_ok=""
    for _ in {1..15}; do
      if [[ -f "$WEB_LOG" ]] && grep -Eiq "Next\.js .+\(${expected_bundler}\)" "$WEB_LOG"; then
        bundler_line_ok="yes"
        break
      fi
      sleep 1
    done
    if [[ -z "$bundler_line_ok" ]]; then
      echo "❌ UI nie potwierdził oczekiwanego bundlera '${expected_bundler}' w logach."
      echo "ℹ️  Ostatnie logi UI:"
      tail -n 60 "$WEB_LOG" || true
      kill_pid_group_graceful "$wpid" "UI"
      rm -f "$WEB_PID_FILE"
      UI_STARTED=0
      exit 1
    fi
  fi

  echo "✅ UI (Next.js) wystartował z PID $(cat "$WEB_PID_FILE")"
fi

echo "🚀 Gotowe: backend http://${HOST_DISPLAY}:${PORT}, dashboard http://${WEB_DISPLAY}:${WEB_PORT}"
START_SUCCESS=1
