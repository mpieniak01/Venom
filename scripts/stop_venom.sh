#!/usr/bin/env bash
# stop_venom.sh - Skrypt do bezpiecznego zatrzymywania stosu Venom

echo "🛑 Zatrzymuję stos Venom (Web, Backend, LLM)..."
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$ROOT_DIR/.venv/bin/python"

kill_tree() {
    local pid="${1:-}"
    local signal="${2:-TERM}"
    [[ -z "$pid" ]] && return 0
    if ! kill -0 "$pid" 2>/dev/null; then
        return 0
    fi

    local child
    for child in $(pgrep -P "$pid" 2>/dev/null || true); do
        kill_tree "$child" "$signal"
    done
    kill "-$signal" "$pid" 2>/dev/null || true
}

stop_pid_file() {
    local pid_file="$1"
    local label="$2"
    if [[ ! -f "$pid_file" ]]; then
        return 0
    fi

    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -n "$pid" ]]; then
        echo "⏹️  Zamykam ${label} (PID $pid)"
        kill_tree "$pid" TERM
        sleep 1
        if kill -0 "$pid" 2>/dev/null; then
            kill_tree "$pid" KILL
        fi
    fi
    rm -f "$pid_file" 2>/dev/null || true
}

# 0. Zatrzymaj potencjalnie wiszące procesy startowe make
pkill -f "make --no-print-directory _start" 2>/dev/null || true

# 1. Frontend (Next.js)
stop_pid_file ".web-next.pid" "Frontend"
pkill -f "next-server" 2>/dev/null || true
pkill -f "next-router-worker" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "next start" 2>/dev/null || true

# 2. Backend (FastAPI)
stop_pid_file ".venom.pid" "Backend"
pkill -f "uvicorn.*venom_core.main:app" 2>/dev/null || true

# 3. LLM Runtime
echo "🧠 Zwalniam zasoby LLM..."
bash scripts/llm/vllm_service.sh stop >/dev/null 2>&1 || true
bash scripts/llm/ollama_service.sh stop >/dev/null 2>&1 || true

# 4. Agresywne czyszczenie zombi (GPU/VRAM)
pkill -9 -f "vllm serve" 2>/dev/null || true
pkill -9 -f "VLLM::EngineCore" 2>/dev/null || true
pkill -9 -f "vllm.entrypoints" 2>/dev/null || true
pkill -9 -f "ray::" 2>/dev/null || true
pkill -9 -f "${VENV_PY} -c from multiprocessing.spawn import spawn_main" 2>/dev/null || true
pkill -9 -f "${VENV_PY} -c from multiprocessing.resource_tracker import main" 2>/dev/null || true

# 5. Czyszczenie portów
PORTS_TO_CLEAN="8000 3000 11434 8001"
if command -v lsof >/dev/null 2>&1; then
    for port in $PORTS_TO_CLEAN; do
        pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            echo "⚠️  Zwalniam port $port (PIDs: $pids)"
            kill $pids 2>/dev/null || true
        fi
    done
elif command -v fuser >/dev/null 2>&1; then
    for port in $PORTS_TO_CLEAN; do
        pids=$(fuser -n tcp "$port" 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            echo "⚠️  Zwalniam port $port przez fuser (PIDs: $pids)"
            fuser -k -n tcp "$port" >/dev/null 2>&1 || true
        fi
    done
fi

echo "✅ System Venom został zatrzymany."
