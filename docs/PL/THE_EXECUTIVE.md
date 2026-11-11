# THE EXECUTIVE - Warstwa Zarządzania i Strategii

## Przegląd

**The Executive** to najwyższa warstwa w hierarchii Venoma, która przekształca system z "wykonawcy zadań" w "zarządcę projektu". Wprowadza autonomiczne zarządzanie projektami z hierarchiczną strukturą celów i automatyczną realizacją roadmapy.

## Architektura

```
┌─────────────────────────────────────────────────────────────┐
│                    THE EXECUTIVE LAYER                       │
│                                                              │
│  ┌────────────────┐    ┌────────────────┐   ┌────────────┐ │
│  │ ExecutiveAgent │───►│   GoalStore    │◄──│  War Room  │ │
│  │   (CEO/PM)     │    │  (Roadmapa)    │   │ Dashboard  │ │
│  └────────────────┘    └────────────────┘   └────────────┘ │
│         │                      │                    │        │
│         └──────────────────────┼────────────────────┘        │
│                                │                              │
└────────────────────────────────┼──────────────────────────────┘
                                 │
                        ┌────────▼────────┐
                        │  Orchestrator   │
                        │  (Campaign Mode)│
                        └─────────────────┘
                                 │
                        ┌────────▼────────┐
                        │  The Council    │
                        │  Architect      │
                        │  Coder          │
                        │  Guardian       │
                        └─────────────────┘
```

## Komponenty

### 1. GoalStore (`venom_core/core/goal_store.py`)

Magazyn hierarchicznej struktury celów projektu.

**Hierarchia:**
- **Vision** (Wizja) - Nadrzędny cel długoterminowy
- **Milestone** (Kamień Milowy) - Etapy realizacji
- **Task** (Zadanie) - Konkretne zadania do wykonania

**KPI (Key Performance Indicators):**
- Metryki sukcesu dla każdego celu
- Automatyczne obliczanie postępu

**Persistencja:**
- JSON storage w `data/memory/roadmap.json`
- Automatyczne zapisywanie zmian

**API:**
```python
goal_store = GoalStore()

# Dodaj wizję
vision = goal_store.add_goal(
    title="Stworzyć najlepszy framework AI",
    goal_type=GoalType.VISION,
    description="...",
    kpis=[KPI(name="Postęp", target_value=100.0, unit="%")]
)

# Dodaj milestone
milestone = goal_store.add_goal(
    title="Wdrożyć Executive Layer",
    goal_type=GoalType.MILESTONE,
    parent_id=vision.goal_id,
    priority=1
)

# Pobierz kolejne zadanie
next_task = goal_store.get_next_task()

# Aktualizuj postęp
goal_store.update_progress(
    task.goal_id,
    status=GoalStatus.COMPLETED
)

# Generuj raport
report = goal_store.generate_roadmap_report()
```

### 2. ExecutiveAgent (`venom_core/agents/executive.py`)

Agent najwyższego szczebla - CEO/Product Manager systemu.

**Rola:**
- Przekształcanie wizji w roadmapę
- Priorytetyzacja zadań
- Zarządzanie zespołem agentów
- Raportowanie statusu projektu

**Kluczowe metody:**
```python
executive = ExecutiveAgent(kernel, goal_store)

# Utwórz roadmapę z wizji
roadmap = await executive.create_roadmap(
    "Chcę stworzyć najlepszy system AI"
)

# Wygeneruj raport statusu
status = await executive.generate_status_report()

# Przeprowadź Daily Standup
meeting = await executive.run_status_meeting()

# Priorytetyzuj zadania
priorities = await executive.prioritize_tasks(milestone_id)
```

### 3. Campaign Mode (Tryb Kampanii)

Autonomiczna pętla realizacji roadmapy w `Orchestrator`.

**Algorytm:**
```
LOOP (max_iterations):
    1. Pobierz kolejne zadanie z GoalStore
    2. Wykonaj zadanie (deleguj do agentów)
    3. Zweryfikuj wyniki (Guardian)
    4. Zaktualizuj postęp w GoalStore
    5. Jeśli Milestone ukończony:
       - Pauza dla akceptacji użytkownika
       - Przejdź do kolejnego Milestone
    6. Jeśli wszystkie cele osiągnięte:
       - SUKCES - zakończ kampanię
```

**Użycie:**
```python
# Uruchom kampanię
result = await orchestrator.execute_campaign_mode(
    goal_store=goal_store,
    max_iterations=10
)
```

### 4. War Room Dashboard (`web/templates/strategy.html`)

Wizualny dashboard strategiczny dla zarządzania projektem.

**Sekcje:**
- **Vision Panel** - Wyświetla główną wizję i postęp
- **Milestones Panel** - Lista kamieni milowych z statusem
- **Tasks List** - Zadania w ramach milestone
- **KPI Dashboard** - Wskaźniki sukcesu
- **Actions** - Przyciski do zarządzania

**Dostęp:**
```
http://localhost:8000/strategy
```

## Workflow

### 1. Definiowanie Wizji

Użytkownik definiuje wizję projektu:

```
"Chcę stworzyć najlepszy framework AI do automatyzacji zadań"
```

ExecutiveAgent automatycznie generuje:
- Vision (Wizja główna)
- 3-5 Milestones (Etapy)
- 3-5 Tasks dla pierwszego Milestone

### 2. Uruchomienie Kampanii

System wchodzi w tryb autonomiczny:

1. **Iteracja 1:**
   - Pobiera Task 1 z Milestone 1
   - Deleguje do Coder/Guardian
   - Testuje i weryfikuje
   - Oznacza jako COMPLETED

2. **Iteracja 2:**
   - Pobiera Task 2
   - ...

3. **Milestone ukończony:**
   - Pauza dla akceptacji
   - Czeka na potwierdzenie użytkownika
   - Przechodzi do Milestone 2

### 3. Daily Standup

Automatyczne spotkanie statusowe (codziennie):

```python
scheduler.schedule_daily_standup(
    executive_agent=executive,
    goal_store=goal_store,
    hour=9,
    minute=0
)
```

Raport zawiera:
- Status aktualnego Milestone
- Ukończone/Pending/Blocked zadania
- Blokery (jeśli są)
- Następne zadanie do realizacji
- Decyzje Executive

### 4. Raportowanie

Generowanie raportów menedżerskich:

```python
report = await executive.generate_status_report()
```

Format:
```
=== ROADMAP PROJEKTU ===

🎯 VISION: Stworzyć najlepszy framework AI
   Status: IN_PROGRESS
   Postęp: 45.0%

📋 KAMIENIE MILOWE (3):

  1. 🔄 [1] Wdrożyć Executive Layer
      Postęp: 90.0% | IN_PROGRESS
      Zadania: 4/5 ukończonych

  2. ⏸️ [2] Zintegrować z GitHub
      Postęp: 0.0% | PENDING
      Zadania: 0/3 ukończonych

📊 PODSUMOWANIE: 0/3 kamieni milowych ukończonych (0.0%)
```

## API Endpoints

### GET /strategy
Serwuje War Room dashboard

### GET /api/roadmap
Pobiera pełną roadmapę
```json
{
  "vision": {...},
  "milestones": [...],
  "kpis": {...},
  "report": "..."
}
```

### POST /api/roadmap/create
Tworzy roadmapę z wizji
```json
{
  "vision": "Stworzyć najlepszy framework AI"
}
```

### GET /api/roadmap/status
Generuje raport statusu Executive

### POST /api/campaign/start
Uruchamia Tryb Kampanii

## Integracja z Intent Manager

Nowe intencje:

**START_CAMPAIGN:**
```
"Rozpocznij kampanię"
"Uruchom tryb autonomiczny"
"Kontynuuj pracę nad projektem"
```

**STATUS_REPORT:**
```
"Jaki jest status projektu?"
"Pokaż postęp"
"Gdzie jesteśmy z realizacją?"
```

## Przykłady użycia

### Scenariusz 1: Nowy projekt

```python
# 1. Użytkownik definiuje wizję
vision = "Stworzyć system monitoringu serwerów"

# 2. Executive tworzy roadmapę
roadmap = await executive.create_roadmap(vision)

# 3. System uruchamia kampanię
campaign = await orchestrator.execute_campaign_mode(goal_store)

# 4. Venom autonomicznie realizuje kolejne zadania
# - Milestone 1: Backend API
#   - Task 1: Setup FastAPI ✅
#   - Task 2: Database models ✅
#   - Task 3: Authentication ✅
# - Milestone 2: Frontend Dashboard
#   ...
```

### Scenariusz 2: Status Check

```
Użytkownik: "Jaki jest status projektu?"

Executive: "Jesteśmy w 60% realizacji Milestone 1 (Backend API).
Ukończono 3/5 zadań. Aktualnie pracujemy nad integracją z bazą danych.
Brak blokerów. Spodziewany completion: ~2 dni."
```

### Scenariusz 3: Human-in-the-loop

```
[Milestone 1 ukończony]

System: "Milestone 1 'Backend API' gotowy. Czy mogę zacząć Milestone 2 'Frontend'?"

Użytkownik: "Tak, kontynuuj"

System: [Rozpoczyna Milestone 2]
```

## Konfiguracja

W `venom_core/config.py`:
```python
# Executive Layer settings
GOAL_STORE_PATH = "data/memory/roadmap.json"
CAMPAIGN_MAX_ITERATIONS = 10
DAILY_STANDUP_HOUR = 9
DAILY_STANDUP_MINUTE = 0
```

## Bezpieczeństwo

- **Human-in-the-loop:** Po każdym Milestone system pauzuje
- **Max iterations:** Limit iteracji zapobiega nieskończonym pętlom
- **Budget control:** Użytkownik kontroluje budżet tokenów
- **Validation:** Guardian weryfikuje każde zadanie

## Zobacz również

- [THE_COUNCIL.md](THE_COUNCIL.md) - Współpraca agentów
- [THE_OVERMIND.md](THE_OVERMIND.md) - System harmonogramowania
- [CORE_NERVOUS_SYSTEM_V1.md](CORE_NERVOUS_SYSTEM_V1.md) - Architektura systemu
