#!/usr/bin/env bash
# Skrypt do sprawdzania zużycia pamięci w WSL
# Pokazuje statystyki z /proc/meminfo i free -h

set -euo pipefail

SEPARATOR_LINE="=============================================="
NOT_RUNNING_MSG="  Not running"

echo "$SEPARATOR_LINE"
echo "WSL Memory Usage Check"
echo "$SEPARATOR_LINE"
echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

echo "=== MEMORY SUMMARY (free -h) ==="
free -h
echo ""

echo "=== DETAILED MEMORY INFO (/proc/meminfo) ==="
echo "Total Memory:"
grep MemTotal /proc/meminfo
echo ""
echo "Free Memory:"
grep MemFree /proc/meminfo
echo ""
echo "Available Memory:"
grep MemAvailable /proc/meminfo
echo ""
echo "Cached:"
grep -E "^Cached:" /proc/meminfo
echo ""
echo "Buffers:"
grep Buffers /proc/meminfo
echo ""
echo "Swap:"
grep -E "^Swap" /proc/meminfo
echo ""

echo "=== TOP 10 MEMORY CONSUMERS ==="
ps aux --sort=-%mem | head -n 11
echo ""

echo "=== VENOM PROCESSES MEMORY ==="
echo "Backend (uvicorn):"
ps aux | grep "[u]vicorn.*venom_core" | awk '{print "  PID:", $2, "MEM:", $4"%", "RSS:", $6, "KB", "CMD:", $11, $12, $13}' || echo "$NOT_RUNNING_MSG"
echo ""

echo "Next.js:"
ps aux | grep -E "[n]ode.*(next|web-next)" | awk '{print "  PID:", $2, "MEM:", $4"%", "RSS:", $6, "KB"}' || echo "$NOT_RUNNING_MSG"
echo ""

echo "vLLM:"
ps aux | grep "[v]llm" | awk '{print "  PID:", $2, "MEM:", $4"%", "RSS:", $6, "KB"}' || echo "$NOT_RUNNING_MSG"
echo ""

echo "Ollama:"
ps aux | grep "[o]llama" | awk '{print "  PID:", $2, "MEM:", $4"%", "RSS:", $6, "KB"}' || echo "$NOT_RUNNING_MSG"
echo ""

echo "$SEPARATOR_LINE"
echo "💡 WSKAZÓWKI:"
echo "$SEPARATOR_LINE"
echo "1. Jeśli pamięć w Windows (Task Manager → vmmem) jest znacznie"
echo "   wyższa niż pokazane tutaj wartości, WSL nie zwolnił pamięci."
echo ""
echo "2. Aby wymusić zwolnienie pamięci:"
echo "   - Z poziomu WSL: bash scripts/wsl/reset_memory.sh"
echo "   - Z poziomu Windows: wsl --shutdown (w PowerShell/CMD)"
echo ""
echo "3. Aby ograniczyć zużycie pamięci WSL, utwórz plik:"
echo "   %USERPROFILE%\\.wslconfig"
echo "   Zobacz: scripts/wsl/wslconfig.example"
echo ""
