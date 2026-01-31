# THE_OVERMIND - Background Lifecycle Management

## Przegląd

THE_OVERMIND to system zarządzania zadaniami w tle, który przekształca Venoma z modelu "Request-Response" w autonomiczny system działający 24/7. System monitoruje zmiany w plikach, automatycznie aktualizuje dokumentację i przeprowadza refaktoryzację w trybie bezczynności.

## Architektura

### 1. BackgroundScheduler (`venom_core/core/scheduler.py`)

System harmonogramowania oparty na APScheduler (AsyncIOScheduler).

**Funkcjonalność:**
- Rejestracja zadań cyklicznych (interval, cron)
- Integracja z FastAPI lifespan (start/stop)
- Pause/Resume wszystkich zadań
- Tracking metadanych zadań

**Domyślne zadania:**
- `consolidate_memory`: Konsolidacja pamięci co 60 minut
- `check_health`: Sprawdzanie zdrowia systemu co 5 minut

**Przykład użycia:**
```python
scheduler = BackgroundScheduler(event_broadcaster=event_broadcaster)
await scheduler.start()

# Dodaj zadanie interwałowe
scheduler.add_interval_job(
    func=my_async_function,
    minutes=30,
    job_id="my_job",
    description="Custom job"
)

# Wstrzymaj wszystkie zadania
await scheduler.pause_all_jobs()

# Wznów zadania
await scheduler.resume_all_jobs()
```

### 2. FileWatcher (`venom_core/perception/watcher.py`)

Obserwator systemu plików oparty na Watchdog.

**Funkcjonalność:**
- Rekursywne monitorowanie workspace
- Debouncing (domyślnie 5 sekund)
- Ignorowanie wzorców (.git, __pycache__, etc.)
- Broadcasting zdarzeń CODE_CHANGED

**Ignorowane wzorce:**
- `.git`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`
- `node_modules`, `.venv`, `venv`, `.idea`, `.vscode`
- `*.pyc`, `*.pyo`, `*.swp`, `*.tmp`

**Monitorowane rozszerzenia:**
- `.py` (Python)
- `.md` (Markdown)

**Przykład użycia:**
```python
async def on_file_change(file_path: str):
    print(f"File changed: {file_path}")

watcher = FileWatcher(
    workspace_root="./workspace",
    on_change_callback=on_file_change,
    event_broadcaster=event_broadcaster
)
await watcher.start()
```

### 3. DocumenterAgent (`venom_core/agents/documenter.py`)

Agent automatycznie aktualizujący dokumentację przy zmianie kodu.

**Funkcjonalność:**
- Wykrywanie zmian w plikach Python
- Analiza diff z GitSkill
- Tworzenie/aktualizacja CHANGELOG_AUTO.md
- Automatyczny commit zmian dokumentacji
- Zapobieganie pętlom (ignoruje zmiany venom-bot)

**Algorytm:**
1. Plik .py się zmienia → FileWatcher wykrywa
2. DocumenterAgent sprawdza diff
3. Analizuje czy zmiana wymaga aktualizacji dokumentacji
4. Aktualizuje docs/CHANGELOG_AUTO.md
5. Commituje: `docs: auto-update documentation for [file]`

**Przykład użycia:**
```python
documenter = DocumenterAgent(
    workspace_root="./workspace",
    git_skill=git_skill,
    event_broadcaster=event_broadcaster
)

# Wywołanie przy zmianie pliku
await documenter.handle_code_change("/path/to/changed_file.py")
```

### 4. Enhanced GardenerAgent (Idle Mode)

Rozszerzony GardenerAgent z funkcjonalnością automatycznej refaktoryzacji.

**Funkcjonalność:**
- Monitorowanie ostatniej aktywności (orchestrator.last_activity)
- Próg bezczynności: 15 minut (konfigurowalny)
- Analiza złożoności cyklomatycznej (radon)
- Tworzenie brancha `refactor/auto-gardening`
- Wybór pliku o najwyższej złożoności

**Algorytm idle mode:**
1. System bezczynny przez 15+ minut
2. GardenerAgent skanuje pliki Python
3. Radon analizuje złożoność cyklomatyczną
4. Wybiera plik o złożoności > 10
5. Tworzy branch `refactor/auto-gardening`
6. (W przyszłości: refaktoryzacja + testy + commit)

**Przykład użycia:**
```python
gardener = GardenerAgent(
    graph_store=graph_store,
    orchestrator=orchestrator,
    event_broadcaster=event_broadcaster
)
await gardener.start()
```

## Konfiguracja

Wszystkie ustawienia w `venom_core/config.py`:

```python
# Globalny wyłącznik zadań w tle
VENOM_PAUSE_BACKGROUND_TASKS: bool = False

# Automatyczna aktualizacja dokumentacji
ENABLE_AUTO_DOCUMENTATION: bool = True

# Automatyczna refaktoryzacja w trybie Idle
ENABLE_AUTO_GARDENING: bool = True

# Czas debounce dla watchdog (sekundy)
WATCHER_DEBOUNCE_SECONDS: int = 5

# Próg bezczynności przed uruchomieniem auto-gardening (minuty)
IDLE_THRESHOLD_MINUTES: int = 15

# Interwał konsolidacji pamięci (minuty)
MEMORY_CONSOLIDATION_INTERVAL_MINUTES: int = 60

# Interwał sprawdzania zdrowia (minuty)
HEALTH_CHECK_INTERVAL_MINUTES: int = 5
```

Można też użyć zmiennych środowiskowych w pliku `.env`:

```bash
VENOM_PAUSE_BACKGROUND_TASKS=true
ENABLE_AUTO_DOCUMENTATION=false
ENABLE_AUTO_GARDENING=true
WATCHER_DEBOUNCE_SECONDS=10
IDLE_THRESHOLD_MINUTES=30
```

## REST API

### Scheduler

**GET /api/v1/scheduler/status**
```json
{
  "status": "success",
  "scheduler": {
    "is_running": true,
    "paused": false,
    "jobs_count": 2,
    "state": "STATE_RUNNING"
  }
}
```

**GET /api/v1/scheduler/jobs**
```json
{
  "status": "success",
  "jobs": [
    {
      "id": "consolidate_memory",
      "next_run_time": "2024-12-07T12:00:00",
      "type": "interval",
      "description": "Konsolidacja pamięci i analiza logów",
      "interval_minutes": 60
    }
  ],
  "count": 2
}
```

**POST /api/v1/scheduler/pause**
```json
{
  "status": "success",
  "message": "All background jobs paused"
}
```

**POST /api/v1/scheduler/resume**
```json
{
  "status": "success",
  "message": "All background jobs resumed"
}
```

### Watcher

**GET /api/v1/watcher/status**
```json
{
  "status": "success",
  "watcher": {
    "is_running": true,
    "workspace_root": "/path/to/workspace",
    "debounce_seconds": 5,
    "monitoring_extensions": [".py", ".md"]
  }
}
```

### Documenter

**GET /api/v1/documenter/status**
```json
{
  "status": "success",
  "documenter": {
    "enabled": true,
    "workspace_root": "/path/to/workspace",
    "processing_files": 0
  }
}
```

### Gardener

**GET /api/v1/gardener/status**
```json
{
  "status": "success",
  "gardener": {
    "is_running": true,
    "last_scan_time": "2024-12-07T11:30:00",
    "scan_interval_seconds": 300,
    "workspace_root": "/path/to/workspace",
    "monitored_files": 42,
    "idle_refactoring_enabled": true,
    "idle_refactoring_in_progress": false
  }
}
```

## WebSocket Events

Nowe typy zdarzeń w `EventType`:

```python
# Zdarzenia Background Tasks
CODE_CHANGED = "CODE_CHANGED"
BACKGROUND_JOB_STARTED = "BACKGROUND_JOB_STARTED"
BACKGROUND_JOB_COMPLETED = "BACKGROUND_JOB_COMPLETED"
BACKGROUND_JOB_FAILED = "BACKGROUND_JOB_FAILED"
DOCUMENTATION_UPDATED = "DOCUMENTATION_UPDATED"
MEMORY_CONSOLIDATED = "MEMORY_CONSOLIDATED"
IDLE_REFACTORING_STARTED = "IDLE_REFACTORING_STARTED"
IDLE_REFACTORING_COMPLETED = "IDLE_REFACTORING_COMPLETED"
```

**Przykład zdarzenia:**
```json
{
  "type": "CODE_CHANGED",
  "agent": null,
  "message": "File changed: main.py",
  "timestamp": "2024-12-07T11:34:00",
  "data": {
    "file_path": "/workspace/main.py",
    "relative_path": "main.py",
    "timestamp": 1733574840.123
  }
}
```

## Dashboard UI

Nowy tab **"⚙️ Jobs"** w prawym panelu:

### Sekcje:

1. **Scheduler Status**
   - Status (Running/Stopped)
   - Liczba zadań
   - Paused (Yes/No)

2. **Active Jobs**
   - Lista aktywnych zadań
   - Next run time dla każdego zadania
   - Typ zadania (interval/cron)

3. **File Watcher**
   - Status (Watching/Stopped)
   - Workspace path
   - Monitorowane rozszerzenia

4. **Auto-Documentation**
   - Enabled/Disabled
   - Liczba przetwarzanych plików

5. **Auto-Gardening**
   - Running status
   - Idle refactoring enabled
   - In progress status
   - Last scan time

### Kontrolki:

- **⏸️ Pause** - Wstrzymanie wszystkich zadań
- **▶️ Resume** - Wznowienie zadań
- **🔄 Refresh** - Odświeżenie statusu

## Scenariusze użycia

### 1. Live Documentation

**Scenariusz:**
1. Zmieniam nazwę funkcji w `venom_core/utils/helpers.py`
2. Zapisuję plik (Ctrl+S)
3. FileWatcher wykrywa zmianę (po 5s debounce)
4. DocumenterAgent analizuje diff
5. Aktualizuje `docs/CHANGELOG_AUTO.md`
6. Commituje: `docs: auto-update documentation for helpers.py`

**Rezultat:** Dokumentacja zawsze aktualna, bez manualnej pracy.

### 2. Refaktoryzacja w tle

**Scenariusz:**
1. Zostawiam Venoma włączonego na noc
2. System bezczynny przez >15 minut
3. GardenerAgent wykrywa idle mode
4. Skanuje workspace radon-em
5. Znajduje `complex_module.py` o złożoności 15
6. Tworzy branch `refactor/auto-gardening`
7. (W przyszłości: refaktoryzuje kod)

**Rezultat:** Rano widzę PR z poprawionym kodem.

### 3. Konsolidacja pamięci

**Scenariusz:**
1. Intensywna sesja kodowania (3h)
2. Co godzinę uruchamia się `consolidate_memory()`
3. (W przyszłości: Analizuje logi, wyciąga wnioski)
4. Zapisuje kluczowe ustalenia do VectorStore

**Rezultat:** Venom "pamięta" kontekst długotrwałych sesji.

## Bezpieczeństwo

### Zapobieganie pętlom

**Problem:** Venom zmienia plik → Watchdog wykrywa → Venom reaguje → pętla

**Rozwiązania:**
1. DocumenterAgent ignoruje zmiany od użytkownika "venom-bot"
2. Tracking ostatnio przetwarzanych plików (60s timeout)
3. Debouncing w FileWatcher (5s ciszy przed reakcją)

### Walidacja ścieżek

Wszystkie endpointy API walidują ścieżki:
- Brak `..` w ścieżce
- Brak absolutnych ścieżek
- Wszystko w ramach workspace_root

### Globalny wyłącznik

`VENOM_PAUSE_BACKGROUND_TASKS=true` wyłącza wszystkie zadania w tle.

## Testy

### Jednostkowe
- `tests/test_scheduler.py` - BackgroundScheduler (7 testów)
- `tests/test_watcher.py` - FileWatcher (6 testów)
- `tests/test_documenter.py` - DocumenterAgent (5 testów)

### Integracyjne
- `tests/test_overmind_integration.py` - Integracja komponentów (6 testów)

**Uruchomienie:**
```bash
pytest tests/test_scheduler.py tests/test_watcher.py -v
pytest tests/test_overmind_integration.py -v
```

## Troubleshooting

### FileWatcher nie wykrywa zmian

**Przyczyny:**
1. Plik w ignorowanych wzorcach (.git, __pycache__)
2. Rozszerzenie inne niż .py lub .md
3. Watcher nie uruchomiony

**Rozwiązanie:**
```bash
# Sprawdź status
curl http://localhost:8000/api/v1/watcher/status

# Sprawdź logi
tail -f logs/venom.log | grep FileWatcher
```

### Zadania w tle nie działają

**Przyczyny:**
1. `VENOM_PAUSE_BACKGROUND_TASKS=true`
2. Scheduler nie uruchomiony
3. Błąd w funkcji zadania

**Rozwiązanie:**
```bash
# Sprawdź status schedulera
curl http://localhost:8000/api/v1/scheduler/status

# Sprawdź listę zadań
curl http://localhost:8000/api/v1/scheduler/jobs

# Wznów zadania
curl -X POST http://localhost:8000/api/v1/scheduler/resume
```

### Dokumentacja nie aktualizuje się

**Przyczyny:**
1. `ENABLE_AUTO_DOCUMENTATION=false`
2. Brak GitSkill (workspace nie jest repo Git)
3. Zmiana dokonana przez venom-bot (ignorowana)

**Rozwiązanie:**
```bash
# Sprawdź status documentera
curl http://localhost:8000/api/v1/documenter/status

# Sprawdź config
grep ENABLE_AUTO_DOCUMENTATION .env
```

## Przyszłe rozszerzenia

1. **Inteligentna refaktoryzacja**
   - Użycie LLM do analizy i przepisania złożonego kodu
   - Automatyczne testy po refaktoryzacji
   - PR z opisem zmian

2. **Konsolidacja pamięci**
   - Analiza logów z semantic_kernel
   - Ekstrakcja kluczowych wniosków
   - Zapis do GraphRAG

3. **Zaawansowane health checks**
   - Sprawdzanie Docker containers
   - Pingowanie LLM endpoints
   - Monitorowanie użycia zasobów

4. **Notyfikacje**
   - Slack/Discord webhooks dla ważnych zdarzeń
   - Email przy wykryciu problemów
   - Dashboard toast notifications

## Zależności

Dodane do `requirements.txt`:
```
apscheduler      # Scheduler zadań w tle
watchdog         # Monitorowanie systemu plików
radon            # Analiza złożoności kodu
```

## Autorzy

- Implementacja: GitHub Copilot (Copilot Workspace)
- Issue: mpieniak01 (#015_THE_OVERMIND)
- Repository: mpieniak01/Venom
