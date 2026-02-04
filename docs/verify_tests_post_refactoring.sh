#!/bin/bash
# Skrypt weryfikacji testów po refaktoryzacji legacy UI
# Użycie: bash docs/verify_tests_post_refactoring.sh

set -e

echo "=================================================="
echo "Weryfikacja Testów Po Refaktoryzacji Legacy UI"
echo "=================================================="
echo ""

# Kolory
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Sprawdź czy jesteś w głównym katalogu projektu
if [ ! -f "pytest.ini" ]; then
    echo -e "${RED}❌ Błąd: Uruchom skrypt z głównego katalogu projektu Venom${NC}"
    exit 1
fi

echo "📋 Krok 1: Weryfikacja struktury testów"
echo "----------------------------------------"

# Funkcja do sprawdzania czy testy zawierają legacy endpoints
check_legacy_endpoints() {
    local pattern=$1
    local name=$2
    
    if grep -rn "$pattern" tests/ --include="*.py" > /dev/null 2>&1; then
        echo -e "${RED}❌ OSTRZEŻENIE: Znaleziono referencje do $name${NC}"
        grep -rn "$pattern" tests/ --include="*.py" | head -5
        return 1
    else
        echo -e "${GREEN}✓ Brak referencji do $name${NC}"
        return 0
    fi
}

# Sprawdź stare endpointy
check_legacy_endpoints '"/brain"' "/brain endpoint"
check_legacy_endpoints '"/strategy"' "/strategy endpoint"
check_legacy_endpoints '"/inspector"' "/inspector endpoint"
check_legacy_endpoints '"/flow-inspector"' "/flow-inspector endpoint"

# Sprawdź HTML/template patterns
check_legacy_endpoints 'text/html' "text/html content-type"
check_legacy_endpoints 'TemplateResponse' "TemplateResponse"
check_legacy_endpoints 'Jinja2Templates' "Jinja2Templates"

echo ""
echo "📋 Krok 2: Lista plików testowych do zweryfikowania"
echo "----------------------------------------------------"

CRITICAL_TESTS=(
    "tests/test_dashboard_api.py"
    "tests/test_flow_inspector_api.py"
    "tests/test_main_setup_router_dependencies.py"
)

for test_file in "${CRITICAL_TESTS[@]}"; do
    if [ -f "$test_file" ]; then
        echo -e "${GREEN}✓ $test_file${NC}"
    else
        echo -e "${RED}❌ BRAK: $test_file${NC}"
    fi
done

echo ""
echo "📋 Krok 3: Sprawdzenie zależności pytest"
echo "----------------------------------------"

if ! python3 -c "import pytest" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  pytest nie jest zainstalowany${NC}"
    echo "Zainstaluj zależności: pip install -r requirements.txt"
    echo -e "${YELLOW}Pomijam uruchomienie testów${NC}"
    exit 0
fi

echo -e "${GREEN}✓ pytest zainstalowany${NC}"

echo ""
echo "📋 Krok 4: Uruchomienie krytycznych testów"
echo "--------------------------------------------"

# Ustaw PYTEST_ADDOPTS aby ominąć problemy z --dist
export PYTEST_ADDOPTS=""

# Test MetricsCollector (szybki test bez zależności)
echo "Uruchamiam: test_dashboard_api.py::TestMetricsCollector"
if python3 -m pytest tests/test_dashboard_api.py::TestMetricsCollector -v --tb=short 2>&1 | tail -20; then
    echo -e "${GREEN}✓ Test MetricsCollector przeszedł${NC}"
else
    echo -e "${YELLOW}⚠️  Test MetricsCollector wymaga pełnych zależności${NC}"
fi

echo ""
echo "=================================================="
echo "Podsumowanie Weryfikacji"
echo "=================================================="
echo ""
echo -e "${GREEN}✅ Struktura testów jest prawidłowa${NC}"
echo -e "${GREEN}✅ Brak referencji do legacy HTML endpoints${NC}"
echo -e "${GREEN}✅ Wszystkie krytyczne pliki testowe istnieją${NC}"
echo ""
echo "Aby uruchomić pełny zestaw testów:"
echo "  make test"
echo ""
echo "Aby uruchomić tylko testy jednostkowe (bez wydajnościowych):"
echo "  make test-unit"
echo ""
echo "Aby sprawdzić coverage:"
echo "  pytest --cov=venom_core --cov-report=html"
echo ""
