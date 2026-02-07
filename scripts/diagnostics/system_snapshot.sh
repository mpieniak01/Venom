#!/usr/bin/env bash
# Skrypt do szybkiej diagnostyki zużycia zasobów systemowych
# Generuje snapshot procesów, pamięci i obciążenia CPU

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
SNAPSHOT_FILE="$LOG_DIR/diag-$TIMESTAMP.txt"
SEPARATOR_LINE="=============================================="

mkdir -p "$LOG_DIR"

echo "📊 Zbieranie danych diagnostycznych..."
echo "📝 Zapisuję do: $SNAPSHOT_FILE"

{
    echo "$SEPARATOR_LINE"
    echo "VENOM SYSTEM SNAPSHOT"
    echo "$SEPARATOR_LINE"
    echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Hostname: $(hostname)"
    echo ""

    echo "=== UPTIME & LOAD ==="
    uptime
    echo ""

    echo "=== MEMORY (free -h) ==="
    free -h
    echo ""

    echo "=== MEMORY DETAILED (/proc/meminfo - top 20 wierszy) ==="
    head -n 20 /proc/meminfo
    echo ""

    echo "=== TOP 15 PROCESÓW (CPU) ==="
    ps aux --sort=-%cpu | head -n 16
    echo ""

    echo "=== TOP 15 PROCESÓW (MEMORY) ==="
    ps aux --sort=-%mem | head -n 16
    echo ""

    echo "=== PROCESY VENOM (uvicorn, python) ==="
    ps aux | grep -E "(uvicorn|venom_core)" | grep -v grep || echo "Brak procesów Venom"
    echo ""

    echo "=== PROCESY NEXT.JS ==="
    ps aux | grep -E "(next|node.*web-next)" | grep -v grep || echo "Brak procesów Next.js"
    echo ""

    echo "=== PROCESY LLM (vllm, ollama) ==="
    ps aux | grep -E "(vllm|ollama)" | grep -v grep || echo "Brak procesów LLM"
    echo ""

    echo "=== DISK USAGE (/) ==="
    df -h / 2>/dev/null || df -h
    echo ""

    echo "=== PID FILES STATUS ==="
    if [[ -f "$ROOT_DIR/.venom.pid" ]]; then
        PID=$(cat "$ROOT_DIR/.venom.pid")
        if kill -0 "$PID" 2>/dev/null; then
            echo "✅ Venom API działa (PID $PID)"
        else
            echo "⚠️  Venom API PID file istnieje, ale proces nie żyje ($PID)"
        fi
    else
        echo "ℹ️  Venom API nie jest uruchomiony"
    fi

    if [[ -f "$ROOT_DIR/.web-next.pid" ]]; then
        WPID=$(cat "$ROOT_DIR/.web-next.pid")
        if kill -0 "$WPID" 2>/dev/null; then
            echo "✅ Next.js działa (PID $WPID)"
        else
            echo "⚠️  Next.js PID file istnieje, ale proces nie żyje ($WPID)"
        fi
    else
        echo "ℹ️  Next.js nie jest uruchomiony"
    fi

    if [[ -f "$LOG_DIR/vllm.pid" ]]; then
        VPID=$(cat "$LOG_DIR/vllm.pid")
        if kill -0 "$VPID" 2>/dev/null; then
            echo "✅ vLLM działa (PID $VPID)"
        else
            echo "⚠️  vLLM PID file istnieje, ale proces nie żyje ($VPID)"
        fi
    else
        echo "ℹ️  vLLM nie jest uruchomiony"
    fi

    if [[ -f "$LOG_DIR/ollama.pid" ]]; then
        OPID=$(cat "$LOG_DIR/ollama.pid")
        if kill -0 "$OPID" 2>/dev/null; then
            echo "✅ Ollama działa (PID $OPID)"
        else
            echo "⚠️  Ollama PID file istnieje, ale proces nie żyje ($OPID)"
        fi
    else
        echo "ℹ️  Ollama nie jest uruchomiony"
    fi

    echo ""
    echo "=== OPEN PORTS (8000, 3000, 8001, 11434) ==="
    if command -v lsof >/dev/null 2>&1; then
        for port in 8000 3000 8001 11434; do
            PIDS=$(lsof -ti tcp:$port 2>/dev/null || true)
            if [[ -n "$PIDS" ]]; then
                # Convert newlines to spaces for ps command
                PIDS_SPACE=$(echo "$PIDS" | tr '\n' ' ')
                echo "Port $port: zajęty przez PID $PIDS_SPACE"
                ps -p $PIDS_SPACE -o pid,comm,args 2>/dev/null || true
            else
                echo "Port $port: wolny"
            fi
        done
    else
        echo "lsof niedostępny - pomijam sprawdzanie portów"
    fi

    echo ""
    echo "$SEPARATOR_LINE"
    echo "KONIEC SNAPSHOTA"
    echo "$SEPARATOR_LINE"

} > "$SNAPSHOT_FILE"

echo "✅ Snapshot zapisany: $SNAPSHOT_FILE"
echo ""
echo "📋 Podsumowanie:"
echo "---"
free -h | grep -E "(Mem|Swap):"
echo "---"
echo "Load average: $(uptime | awk -F'load average:' '{print $2}')"
echo ""
echo "💡 Aby zobaczyć pełny raport: cat $SNAPSHOT_FILE"
