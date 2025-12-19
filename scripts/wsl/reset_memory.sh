#!/usr/bin/env bash
# Skrypt do resetowania pamięci WSL poprzez wywołanie wsl.exe --shutdown
# UWAGA: To zatrzyma wszystkie dystrybucje WSL!

set -euo pipefail

echo "=============================================="
echo "WSL Memory Reset Helper"
echo "=============================================="
echo ""
echo "⚠️  UWAGA: Ten skrypt zatrzyma WSZYSTKIE dystrybucje WSL!"
echo ""

# Sprawdź czy jesteśmy w WSL
if [ ! -f /proc/sys/fs/binfmt_misc/WSLInterop ]; then
    echo "❌ Ten skrypt działa tylko w środowisku WSL"
    exit 1
fi

echo "Aktualne zużycie pamięci:"
free -h | grep -E "(Mem|Swap):"
echo ""

echo "Procesy Venom:"
ps aux | grep -E "(uvicorn|venom_core|next|vllm|ollama)" | grep -v grep || echo "Brak aktywnych procesów Venom"
echo ""

read -p "Czy chcesz zatrzymać wszystkie procesy Venom przed shutdown? (t=tak, n=nie): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[TtYy]$ ]]; then
    echo "🛑 Zatrzymuję procesy Venom..."

    # Zatrzymaj przez Makefile jeśli dostępny
    if [ -f "$(dirname "${BASH_SOURCE[0]}")/../../Makefile" ]; then
        cd "$(dirname "${BASH_SOURCE[0]}")/../.."
        make stop 2>/dev/null || true
    else
        # Manual cleanup
        pkill -f "uvicorn.*venom_core" 2>/dev/null || true
        pkill -f "next" 2>/dev/null || true
        pkill -f "vllm" 2>/dev/null || true
        pkill -f "ollama" 2>/dev/null || true
    fi

    echo "✅ Procesy zatrzymane"
    sleep 2
fi

echo ""
echo "🔄 Wywołuję wsl.exe --shutdown..."
echo ""
echo "💡 Po wykonaniu tej komendy WSL zostanie zamknięty."
echo "   Aby kontynuować pracę, ponownie uruchom terminal WSL."
echo ""

read -p "Kontynuować? (t=tak, n=nie): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[TtYy]$ ]]; then
    # Wywołaj wsl.exe --shutdown z Windows
    if command -v wsl.exe >/dev/null 2>&1; then
        wsl.exe --shutdown
        echo "✅ Komenda wsl.exe --shutdown wywołana"
        echo "   WSL zostanie zamknięty za chwilę..."
    elif command -v powershell.exe >/dev/null 2>&1; then
        powershell.exe -Command "wsl --shutdown"
        echo "✅ Komenda wsl --shutdown wywołana przez PowerShell"
        echo "   WSL zostanie zamknięty za chwilę..."
    else
        echo ""
        echo "❌ Nie można znaleźć wsl.exe ani powershell.exe"
        echo ""
        echo "Wykonaj manualnie z poziomu Windows (PowerShell/CMD):"
        echo "  wsl --shutdown"
        echo ""
    fi
else
    echo "Anulowano."
fi
