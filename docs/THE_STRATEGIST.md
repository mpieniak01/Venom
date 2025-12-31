# THE STRATEGIST - Task Planning & Complexity Management

## Rola

Strategist Agent to planista i analityk złożoności w systemie Venom, odpowiedzialny za ocenę trudności zadań, zarządzanie progresem, wykrywanie scope creep oraz optymalizację wykorzystania zasobów (API calls, tokeny).

## Odpowiedzialności

- **Ocena złożoności** - Klasyfikacja zadań jako TRIVIAL, SIMPLE, MODERATE, COMPLEX, VERY_COMPLEX
- **Dzielenie zadań** - Rozbijanie dużych zadań na mniejsze, wykonalne części
- **Monitorowanie postępu** - Śledzenie wykonania vs. oszacowania (overrun detection)
- **Zarządzanie budżetem** - Kontrola limitów API calls i tokenów
- **Ostrzeganie** - Alerty o scope creep, przekroczeniu budżetu

## Kluczowe Komponenty

### 1. Work Ledger (`venom_core/ops/work_ledger.py`)

**Rola:** Księga zadań i postępu projektu.

**Funkcjonalność:**
- Rejestracja zadań z oszacowaniami złożoności
- Śledzenie statusu (PLANNED, IN_PROGRESS, COMPLETED, FAILED)
- Porównanie rzeczywistego czasu vs. oszacowanie
- Wykrywanie overrun (przekroczenie budżetu)
- Eksport raportów (JSON)

**Przykład użycia:**
```python
from venom_core.ops.work_ledger import WorkLedger, TaskComplexity

ledger = WorkLedger()

# Rejestracja zadania
task_id = ledger.register_task(
    description="Implementacja REST API",
    estimated_complexity=TaskComplexity.MODERATE,
    estimated_time_minutes=120
)

# Aktualizacja statusu
ledger.start_task(task_id)
# ... praca ...
ledger.complete_task(task_id, success=True)

# Raport
report = ledger.generate_report()
print(f"Ukończone zadania: {report['completed_tasks']}")
print(f"Czas total: {report['total_time_minutes']} min")
```

### 2. Complexity Skill (`venom_core/execution/skills/complexity_skill.py`)

**Rola:** Narzędzie do oceny złożoności zadań.

**Funkcjonalność:**
- `estimate_complexity(task_description)` - Ocena złożoności (1-5)
- `split_task(task_description)` - Podział na subtasks
- `detect_scope_creep(original_task, current_task)` - Wykrywanie rozszerzenia zakresu

**Skala złożoności:**
```python
class TaskComplexity(Enum):
    TRIVIAL = 1       # <15 min  - "Wyświetl Hello World"
    SIMPLE = 2        # 15-30 min - "Stwórz plik z funkcją"
    MODERATE = 3      # 30-90 min - "REST API z 3 endpointami"
    COMPLEX = 4       # 1.5-3h - "Aplikacja TODO z DB"
    VERY_COMPLEX = 5  # >3h - "Sklep e-commerce z płatnościami"
```

### 3. API Budget Management

**Limity domyślne (dziennie):**
```python
DEFAULT_API_LIMITS = {
    "openai": {
        "calls": 1000,
        "tokens": 1_000_000
    },
    "anthropic": {
        "calls": 500,
        "tokens": 500_000
    },
    "google": {
        "calls": 1000,
        "tokens": 1_000_000
    }
}
```

**Monitorowanie:**
- Tracking liczby wywołań API per provider
- Tracking liczby tokenów (input + output)
- Alerty przy zbliżaniu się do limitu (>80%)
- Blokada przy przekroczeniu (wymaga aprobacji)

## Integracja z Systemem

### Przepływ Wykonania

```
Użytkownik: "Stwórz sklep e-commerce"
        ↓
StrategistAgent.estimate_complexity()
        → VERY_COMPLEX (5/5)
        ↓
StrategistAgent.split_task()
        → [
            "Backend API (COMPLEX)",
            "Frontend (COMPLEX)",
            "System płatności (MODERATE)",
            "Baza produktów (MODERATE)"
          ]
        ↓
WorkLedger.register_task(parent_task)
WorkLedger.register_task(subtask_1)
...
        ↓
ArchitectAgent planuje każdy subtask osobno
        ↓
Monitoring wykonania przez Work Ledger
        ↓
Raport końcowy (czas, koszty, sukces)
```

### Współpraca z Innymi Agentami

- **ArchitectAgent** - Otrzymuje oszacowania i podziały zadań
- **Orchestrator** - Raportuje przekroczenia budżetu i scope creep
- **AnalystAgent** - Dostarcza metryki kosztów i wydajności
- **IntentManager** - Klasyfikuje intencje jako SIMPLE vs COMPLEX

## Przykłady Użycia

### Przykład 1: Ocena Złożoności
```python
strategist = StrategistAgent(kernel=kernel)

complexity = await strategist.estimate_complexity(
    "Stwórz stronę HTML z zegarem cyfrowym"
)
# → TaskComplexity.SIMPLE (2/5)

complexity = await strategist.estimate_complexity(
    "Zbuduj platformę e-learningową z videami i quizami"
)
# → TaskComplexity.VERY_COMPLEX (5/5)
```

### Przykład 2: Podział Zadania
```python
subtasks = await strategist.split_task(
    "Stwórz aplikację TODO z FastAPI i PostgreSQL"
)
# → [
#     "Setup FastAPI + PostgreSQL (Docker Compose)",
#     "Modele SQLAlchemy dla TODO",
#     "Endpoints CRUD (GET, POST, PUT, DELETE)",
#     "Testy jednostkowe",
# ]
```

### Przykład 3: Wykrywanie Scope Creep
```python
original = "Stwórz prostą stronę HTML"
current = "Stwórz responsywną stronę z animacjami, formami i integracją API"

scope_creep = await strategist.detect_scope_creep(original, current)
if scope_creep:
    # Alert: "Zadanie rozrosło się poza pierwotny zakres!"
```

## Konfiguracja

```bash
# W .env (brak dedykowanych flag dla Strategist)
# API Limits konfigurowane w kodzie lub przez environment variables

# Przykładowe custom limity:
OPENAI_DAILY_CALLS_LIMIT=500
OPENAI_DAILY_TOKENS_LIMIT=500000
```

## Metryki i Monitoring

**Kluczowe wskaźniki:**
- Średnia dokładność oszacowań (actual_time / estimated_time)
- Współczynnik overrun (% zadań przekraczających oszacowanie)
- Wykorzystanie API (calls/day, tokens/day per provider)
- Liczba zadań ze scope creep (% zadań)

**Raporty Work Ledger:**
```json
{
  "total_tasks": 15,
  "completed_tasks": 12,
  "failed_tasks": 1,
  "in_progress": 2,
  "total_time_minutes": 340,
  "average_complexity": 2.8,
  "overrun_tasks": 3
}
```

## Best Practices

1. **Szacuj przed planowaniem** - Zawsze wywołaj `estimate_complexity()` przed ArchitectAgent
2. **Dziel duże zadania** - VERY_COMPLEX (5/5) → split_task() → mniejsze części
3. **Monitoruj budżet** - Sprawdzaj API usage co 100 requestów
4. **Dokumentuj overrun** - Zapisz przyczynę przekroczenia czasu
5. **Scope freeze** - Po akceptacji planu nie rozszerzaj zakresu bez aprobacji

## Znane Ograniczenia

- Oszacowania oparte na heurystykach LLM (nie zawsze precyzyjne)
- Brak integracji z rzeczywistymi kosztami API (tylko tracking calls/tokens)
- Work Ledger trzymany w pamięci (resetuje się po restarcie)
- Brak automatycznej re-estymacji po wykryciu overrun

## Zobacz też

- [THE_ARCHITECT.md](THE_ARCHITECT.md) - Planowanie zadań
- [THE_HIVE.md](THE_HIVE.md) - Rozproszone wykonanie zadań
- [COST_GUARD.md](COST_GUARD.md) - Ochrona budżetu API
- [AGENTS_INDEX.md](AGENTS_INDEX.md) - Pełny indeks agentów
