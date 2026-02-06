#!/usr/bin/env bash
# stop_venom.sh - Skrypt do bezpiecznego zatrzymywania stosu Venom

echo "🛑 Zatrzymuję stos Venom (Web, Backend, LLM)..."

# 0. Zatrzymaj potencjalnie wiszące procesy startowe make
pkill -f "make --no-print-directory _start" 2>/dev/null || true

# 1. Frontend (Next.js)
if [[ -f .web-next.pid ]]; then
    WPID=$(cat .web-next.pid)
    echo "⏹️  Zamykam Frontend (PID $WPID)"
    kill "$WPID" 2>/dev/null || true
    rm -f .web-next.pid 2>/dev/null || true
fi
pkill -f "next-server" 2>/dev/null || true
pkill -f "next-router-worker" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "next start" 2>/dev/null || true

# 2. Backend (FastAPI)
if [[ -f .venom.pid ]]; then
    PID=$(cat .venom.pid)
    echo "⏹️  Zamykam Backend (PID $PID)"
    kill "$PID" 2>/dev/null || true
    rm -f .venom.pid 2>/dev/null || true
fi
pkill -f "uvicorn.*venom_core.main:app" 2>/dev/null || true

# 3. LLM Runtime
echo "🧠 Zwalniam zasoby LLM..."
bash scripts/llm/vllm_service.sh stop >/dev/null 2>&1 || true
bash scripts/llm/ollama_service.sh stop >/dev/null 2>&1 || true

# 4. Agresywne czyszczenie zombi (GPU/VRAM)
pkill -9 -f "vllm serve" 2>/dev/null || true
pkill -9 -f "vllm.entrypoints" 2>/dev/null || true
pkill -9 -f "ray::" 2>/dev/null || true

# 5. Czyszczenie portów
if command -v lsof >/dev/null 2>&1; then
    for port in 8000 3000 11434 8001; do
        pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            echo "⚠️  Zwalniam port $port (PIDs: $pids)"
            kill $pids 2>/dev/null || true
        fi
    done
elif command -v fuser >/dev/null 2>&1; then
    for port in 8000 3000 11434 8001; do
        pids=$(fuser -n tcp "$port" 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            echo "⚠️  Zwalniam port $port przez fuser (PIDs: $pids)"
            fuser -k -n tcp "$port" >/dev/null 2>&1 || true
        fi
    done
fi

echo "✅ System Venom został zatrzymany."
