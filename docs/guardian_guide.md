# THE_GUARDIAN - Autonomous Testing & Self-Healing Pipeline

## Przegląd

THE_GUARDIAN to system automatycznego testowania i samonaprawy kodu zaimplementowany w Venom. System realizuje pętlę "Test-Diagnose-Fix" pozwalającą na autonomiczne wykrywanie i naprawianie błędów w kodzie.

## Komponenty

### 1. TestSkill (`venom_core/execution/skills/test_skill.py`)

Skill odpowiedzialny za uruchamianie testów i lintera w izolowanym środowisku Docker.

**Funkcje:**
- `run_pytest(test_path, timeout)` - Uruchamia testy pytest w kontenerze
- `run_linter(path, timeout)` - Uruchamia linter (ruff lub flake8)

**Przykład użycia:**
```python
from venom_core.execution.skills.test_skill import TestSkill
from venom_core.infrastructure.docker_habitat import DockerHabitat

habitat = DockerHabitat()
test_skill = TestSkill(habitat=habitat)

# Uruchom testy
result = await test_skill.run_pytest(test_path="tests/")
print(result)
```

**Raport testów:**
```
✅ TESTY PRZESZŁY POMYŚLNIE

Passed: 5
Failed: 0
```

lub

```
❌ TESTY NIE PRZESZŁY

Exit Code: 1
Passed: 2
Failed: 1

BŁĘDY:
1. FAILED tests/test_example.py::test_divide - AssertionError
```

### 2. GuardianAgent (`venom_core/agents/guardian.py`)

Agent QA odpowiedzialny za analizę wyników testów i tworzenie ticketów naprawczych.

**Rola:**
- NIE pisze nowego kodu
- Analizuje wyniki testów i traceback
- Diagnozuje przyczyny błędów
- Tworzy precyzyjne tickety naprawcze dla CoderAgent

**Przykład użycia:**
```python
from venom_core.agents.guardian import GuardianAgent

guardian = GuardianAgent(kernel=kernel, test_skill=test_skill)

# Przeanalizuj wyniki testów
result = await guardian.process("Uruchom testy i przeanalizuj wyniki")

# Lub stwórz ticket naprawczy bezpośrednio
ticket = await guardian.analyze_test_failure(
    test_output="FAILED test.py - AssertionError: Expected 10, got 0"
)
```

**Format ticketu naprawczego:**
```
FILE: src/calculator.py
LINE: 15
ERROR: AssertionError: Expected 10, got 0
CAUSE: Funkcja divide() zwraca 0 zamiast wyniku dzielenia
ACTION: Popraw logikę dzielenia - upewnij się że zwracasz a/b zamiast 0
```

### 3. Healing Cycle (Pętla Samonaprawy)

Zaimplementowana w `Orchestrator.execute_healing_cycle()`.

**Algorytm:**

```
Iteracja 1-3:
    ┌─────────────────────┐
    │ PHASE 1: CHECK      │
    │ Guardian uruchamia  │
    │ testy w Docker      │
    └──────┬──────────────┘
           │
           ├─ exit_code == 0? ──> ✅ SUKCES (koniec)
           │
           └─ exit_code != 0
                    │
           ┌────────▼─────────────┐
           │ PHASE 2: DIAGNOSE    │
           │ Guardian analizuje   │
           │ błąd i tworzy ticket │
           └────────┬─────────────┘
                    │
           ┌────────▼─────────────┐
           │ PHASE 3: FIX         │
           │ Coder generuje       │
           │ poprawkę             │
           └────────┬─────────────┘
                    │
           ┌────────▼─────────────┐
           │ PHASE 4: APPLY       │
           │ Kod jest zapisywany  │
           └────────┬─────────────┘
                    │
                    └─> Powrót do PHASE 1

Po 3 iteracjach: ⚠️ FAIL FAST - Wymaga interwencji ręcznej
```

**Przykład użycia:**
```python
from venom_core.core.orchestrator import Orchestrator

orchestrator = Orchestrator(state_manager, ...)

# Uruchom pętlę samonaprawy dla zadania
result = await orchestrator.execute_healing_cycle(
    task_id=task_id,
    test_path="tests/"
)

if result["success"]:
    print(f"✅ Testy przeszły po {result['iterations']} iteracjach")
else:
    print(f"⚠️ {result['message']}")
```

## Integracja z Dashboard

System wysyła zdarzenia WebSocket do dashboardu w czasie rzeczywistym.

### Nowe typy zdarzeń:

- `HEALING_STARTED` - Rozpoczęcie pętli samonaprawy
- `TEST_RUNNING` - Uruchamianie testów (z numerem iteracji)
- `TEST_RESULT` - Wynik testów (sukces/porażka)
- `HEALING_FAILED` - Niepowodzenie po 3 iteracjach
- `HEALING_ERROR` - Błąd podczas procesu

### Wizualizacja w UI:

Dashboard wyświetla:
- 🟢 Zielony pasek dla testów które przeszły
- 🔴 Czerwony pasek dla testów które nie przeszły
- Licznik iteracji
- Powiadomienia toast o postępach
- Logi w czasie rzeczywistym

## Konfiguracja

### Wymagania środowiska:

1. **Docker** - Wymagany do uruchomienia DockerHabitat
2. **Python 3.11+**
3. **Zależności w kontenerze:**
   - pytest
   - ruff lub flake8

### Ustawienia:

```python
# Maksymalna liczba iteracji naprawy
MAX_HEALING_ITERATIONS = 3

# Timeout dla testów (sekundy)
TEST_TIMEOUT = 60

# Timeout dla instalacji zależności
INSTALL_TIMEOUT = 120
```

## Przykładowy scenariusz użycia

### 1. Użytkownik prosi o funkcję z błędem:

```
User: "Napisz funkcję divide(a, b) która dzieli dwie liczby"
```

### 2. CoderAgent generuje kod z błędem:

```python
def divide(a, b):
    return 0  # Bug: zawsze zwraca 0
```

### 3. Guardian uruchamia testy:

```
❌ TESTY NIE PRZESZŁY
FAILED test_calculator.py::test_divide - AssertionError: Expected 5, got 0
```

### 4. Guardian diagnozuje:

```
FILE: calculator.py
LINE: 2
CAUSE: Funkcja zawsze zwraca 0 zamiast wyniku dzielenia
ACTION: Zmień return 0 na return a / b
```

### 5. Coder naprawia:

```python
def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
```

### 6. Guardian uruchamia testy ponownie:

```
✅ TESTY PRZESZŁY POMYŚLNIE
Passed: 3
Failed: 0
```

### 7. System raportuje sukces:

```
✅ Kod naprawiony automatycznie w 2 iteracjach
```

## Bezpieczeństwo

### Izolacja:
- Wszystkie testy uruchamiane WYŁĄCZNIE w kontenerze Docker
- Host nie musi mieć zainstalowanego pytest
- Izolacja procesów i systemu plików

### Timeouty:
- Ochrona przed zawieszeniem testów (60s)
- Ochrona przed zawieszeniem instalacji (120s)

### Fail Fast:
- Maksymalnie 3 iteracje naprawy
- Po przekroczeniu limitu - wymaga interwencji ręcznej
- Zapobiega nieskończonym pętlom

## Metryki i monitoring

System zbiera metryki:
- Liczba uruchomień pętli samonaprawy
- Średnia liczba iteracji do sukcesu
- Współczynnik automatycznej naprawy (%)
- Czas trwania każdej iteracji

Dostępne przez:
- Dashboard (Live Feed)
- WebSocket events
- Logi systemowe

## Rozwój

### Planowane ulepszenia:

1. **Inteligentne cachowanie:**
   - Zapamiętywanie podobnych błędów
   - Szybsze diagnozy dla znanych problemów

2. **Analiza coverage:**
   - Sprawdzanie pokrycia testami
   - Sugerowanie nowych testów

3. **Integracja CI/CD:**
   - Automatyczne uruchamianie przed commitem
   - Blokada merge przy nieprzechodzących testach

4. **Rozszerzona diagnostyka:**
   - Analiza performance
   - Wykrywanie memory leaks
   - Analiza bezpieczeństwa

## Troubleshooting

### Problem: "Docker nie jest dostępny"
**Rozwiązanie:** Upewnij się że Docker daemon działa: `docker ps`

### Problem: "Testy się zawieszają"
**Rozwiązanie:** Zwiększ timeout w `execute_healing_cycle` lub sprawdź czy testy nie czekają na input

### Problem: "Nie udało się naprawić po 3 iteracjach"
**Rozwiązanie:** To normalne dla skomplikowanych problemów. Sprawdź logi w Live Feed i napraw manualnie.

### Problem: "Linter nie działa"
**Rozwiązanie:** Upewnij się że ruff lub flake8 jest zainstalowany w kontenerze Docker

## Licencja

Ten komponent jest częścią projektu Venom i jest objęty tą samą licencją co projekt macierzysty.
