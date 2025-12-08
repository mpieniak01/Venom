# THE DREAMER - Przewodnik Silnika Snów

## Wprowadzenie

**THE DREAMER** (Synthetic Experience Replay & Imagination Engine) to rewolucyjny system "aktywnego śnienia" w Venomie. W czasie bezczynności lub w godzinach nocnych, Venom wykorzystuje wiedzę zdobytą przez Wyrocznię (Oracle) do generowania hipotetycznych scenariuszy programistycznych, rozwiązuje je w odizolowanym środowisku, a w przypadku sukcesu automatycznie dodaje te doświadczenia do swojego zbioru treningowego.

## Architektura

### Komponenty

1. **DreamEngine** (`venom_core/core/dream_engine.py`)
   - Główny silnik orchestrujący proces śnienia
   - Zarządza fazami REM (Rapid Eye Movement)
   - Integruje wszystkie komponenty w spójny workflow

2. **ScenarioWeaver** (`venom_core/simulation/scenario_weaver.py`)
   - Agent kreatywny generujący zadania programistyczne
   - Używa Few-Shot Chain of Thought dla jakości
   - Tworzy realistyczne test cases

3. **EnergyManager** (`venom_core/core/energy_manager.py`)
   - Monitoruje zasoby systemowe (CPU, RAM, temperatura)
   - Wykrywa aktywność użytkownika
   - Natychmiastowo przerywa śnienie gdy użytkownik wraca

4. **Guardian** (rozszerzony)
   - Ultra-surowa walidacja kodu syntetycznego
   - 100% próg jakości dla zapisywanych snów
   - Integracja z LessonsStore

## Workflow Śnienia

### Faza 1: Trigger
Śnienie może być uruchomione przez:
- **Nightly Dreams**: Harmonogram cron (np. 2:00-6:00)
- **Idle Dreams**: Po 30 minutach bezczynności
- **Ręcznie**: API call do `enter_rem_phase()`

### Faza 2: Pobranie Wiedzy
```python
# DreamEngine pobiera klastry wiedzy z GraphRAG
knowledge_fragments = await dream_engine._get_knowledge_clusters(count=10)
# Fragmenty są sortowane po ważności (liczba połączeń w grafie)
```

### Faza 3: Generowanie Scenariuszy
```python
# ScenarioWeaver tworzy zadania programistyczne
scenarios = await scenario_weaver.weave_multiple_scenarios(
    knowledge_fragments, 
    count=10, 
    difficulty="medium"
)
```

**Przykład wygenerowanego scenariusza:**
```json
{
  "title": "Concurrent Web Scraper z Rate Limiting",
  "description": "Scraper pobierający 50 stron jednocześnie z limitem 5 requestów/sekundę",
  "task_prompt": "Napisz async scraper używając aiohttp...",
  "test_cases": [
    "Wszystkie 50 URLs pobrane w <15 sekund",
    "Rate limiting: max 5 requestów w tym samym czasie",
    "Timeout po 5 sekundach dla pojedynczego URL"
  ],
  "difficulty": "complex",
  "libraries": ["aiohttp", "asyncio"]
}
```

### Faza 4: Realizacja Snu
```python
# Dla każdego scenariusza:
# 1. CoderAgent generuje kod
code = await coder_agent.process(scenario.task_prompt)

# 2. Guardian waliduje (ultra-surowy tryb)
validation = await guardian_agent.process(validation_prompt)

# 3. Jeśli PASS -> zapis do LessonsStore + synthetic_training/
if is_valid:
    lessons_store.add_lesson(
        situation=scenario.description,
        action=code,
        result="✅ Sukces",
        tags=["synthetic", "dream", *scenario.libraries],
        metadata={"synthetic": True}
    )
```

### Faza 5: Przerwanie (Wake Up)
```python
# EnergyManager monitoruje zasoby w tle
if cpu_usage > 70% or user_active:
    await energy_manager.wake_up()
    # → dream_engine.state = INTERRUPTED
    # → wszystkie procesy śnienia zatrzymane w <2s
```

## Konfiguracja

### Plik `.env`
```bash
# THE DREAMER Configuration
ENABLE_DREAMING=true
DREAMING_IDLE_THRESHOLD_MINUTES=30
DREAMING_NIGHT_HOURS=2-6
DREAMING_MAX_SCENARIOS=10
DREAMING_CPU_THRESHOLD=0.7
DREAMING_MEMORY_THRESHOLD=0.8
DREAMING_SCENARIO_COMPLEXITY=medium
DREAMING_VALIDATION_STRICT=true
DREAMING_OUTPUT_DIR=./data/synthetic_training
DREAMING_DOCKER_NAMESPACE=venom-dream-worker
DREAMING_PROCESS_PRIORITY=19
```

### Parametry

| Parametr | Opis | Domyślna wartość |
|----------|------|------------------|
| `ENABLE_DREAMING` | Włącz/wyłącz system śnienia | `false` |
| `DREAMING_IDLE_THRESHOLD_MINUTES` | Czas bezczynności przed śnieniem | `30` |
| `DREAMING_NIGHT_HOURS` | Godziny nocnego śnienia | `"2-6"` |
| `DREAMING_MAX_SCENARIOS` | Maks. scenariuszy na sesję | `10` |
| `DREAMING_CPU_THRESHOLD` | Próg CPU dla przerwania (0-1) | `0.7` |
| `DREAMING_MEMORY_THRESHOLD` | Próg RAM dla przerwania (0-1) | `0.8` |
| `DREAMING_SCENARIO_COMPLEXITY` | Złożoność: simple/medium/complex | `"medium"` |
| `DREAMING_VALIDATION_STRICT` | Ultra-surowa walidacja | `true` |
| `DREAMING_OUTPUT_DIR` | Katalog wyjściowy | `./data/synthetic_training` |
| `DREAMING_DOCKER_NAMESPACE` | Namespace dla kontenerów | `"venom-dream-worker"` |
| `DREAMING_PROCESS_PRIORITY` | Priorytet procesu (0-19) | `19` |

## Użycie

### 1. Harmonogramowanie Nocnego Śnienia

```python
from venom_core.core.scheduler import BackgroundScheduler
from venom_core.core.dream_engine import DreamEngine

# Inicjalizacja
scheduler = BackgroundScheduler()
dream_engine = DreamEngine(kernel, graph_rag, lessons_store, energy_manager)

# Zaplanuj nocne śnienie (2:00-6:00)
await scheduler.start()
scheduler.schedule_nightly_dreaming(
    dream_engine, 
    start_hour=2, 
    end_hour=6
)
```

### 2. Harmonogramowanie Idle Śnienia

```python
# Sprawdzaj bezczynność co 5 minut
scheduler.schedule_idle_dreaming(
    dream_engine, 
    check_interval_minutes=5
)
```

### 3. Ręczne Uruchomienie

```python
# Uruchom sesję śnienia ręcznie
report = await dream_engine.enter_rem_phase(
    max_scenarios=5,
    difficulty="medium"
)

print(report)
# {
#   "session_id": "abc123...",
#   "status": "completed",
#   "duration_seconds": 180,
#   "dreams_attempted": 5,
#   "dreams_successful": 4,
#   "success_rate": 0.8
# }
```

### 4. Monitoring Statusu

```python
# Status EnergyManager
energy_status = energy_manager.get_status()
print(f"CPU: {energy_status['cpu_percent']}%")
print(f"Is Idle: {energy_status['is_idle']}")

# Statystyki DreamEngine
dream_stats = dream_engine.get_statistics()
print(f"Total Dreams: {dream_stats['total_dreams']}")
print(f"Success Rate: {dream_stats['success_rate']:.2%}")
print(f"Saved Dreams: {dream_stats['saved_dreams_count']}")
```

## Struktura Danych Wyjściowych

### Katalog `data/synthetic_training/`
```
data/synthetic_training/
├── dream_abc123.py          # Wygenerowany kod
├── dream_abc123.json        # Metadane
├── dream_def456.py
├── dream_def456.json
└── ...
```

### Przykład `dream_abc123.json`
```json
{
  "dream_id": "abc123",
  "session_id": "xyz789",
  "scenario": {
    "title": "Concurrent Web Scraper z Rate Limiting",
    "description": "Scraper pobierający 50 stron...",
    "difficulty": "complex",
    "libraries": ["aiohttp", "asyncio"],
    "test_cases": [...]
  },
  "code_file": "dream_abc123.py",
  "timestamp": "2024-01-15T02:15:30.123Z",
  "synthetic": true
}
```

### Integracja z LessonsStore

Sny są automatycznie dodawane do `LessonsStore` z flagą `synthetic: true`:

```python
lesson = lessons_store.get_lesson(lesson_id)
print(lesson.tags)  # ["synthetic", "dream", "aiohttp", "asyncio"]
print(lesson.metadata["synthetic"])  # True
```

### Integracja z DatasetCurator

Syntetyczne przykłady są oznaczane w zbiorze treningowym:

```python
curator = DatasetCurator(lessons_store=lessons_store)
curator.collect_from_lessons()

for example in curator.examples:
    if example.metadata.get("synthetic"):
        print(f"Synthetic example: {example.instruction}")
```

## Najlepsze Praktyki

### 1. Zarządzanie Zasobami
- **Ustaw realistyczne progi**: CPU/RAM thresholds powinny pozostawiać margines dla użytkownika
- **Używaj niskiego priorytetu**: `DREAMING_PROCESS_PRIORITY=19` (Linux nice value)
- **Monitoruj temperaturę**: EnergyManager automatycznie sprawdza temp CPU

### 2. Jakość Scenariuszy
- **Używaj GraphRAG**: Upewnij się że graf wiedzy jest bogaty
- **Dostosuj złożoność**: `simple` dla szybkiego uczenia, `complex` dla zaawansowanych przypadków
- **Weryfikuj Few-Shot examples**: ScenarioWeaver używa examples w promptach

### 3. Walidacja
- **ZAWSZE włącz strict validation**: `DREAMING_VALIDATION_STRICT=true`
- **Nie wyłączaj Guardian**: To jedyny filtr jakości
- **Monitoruj success rate**: Niska wartość może oznaczać problemy z konfiguracją

### 4. Bezczynność
- **Odpowiednie thresholdy**: 30 min to dobry balans
- **Unikaj konfliktów**: Nie planuj snów w godzinach pracy
- **Test wake_up**: Sprawdź czy przerwanie działa w <2s

## Troubleshooting

### Problem: Brak snów w `data/synthetic_training/`
**Przyczyna**: Graf wiedzy pusty lub walidacja zawsze failuje  
**Rozwiązanie**:
```python
# Sprawdź graf wiedzy
stats = graph_rag.get_stats()
print(stats["total_nodes"])  # Powinno być >0

# Sprawdź logi Guardian
tail -f logs/venom.log | grep Guardian
```

### Problem: Śnienie nie przerywa się gdy użytkownik wraca
**Przyczyna**: EnergyManager nie monitoruje lub progi za wysokie  
**Rozwiązanie**:
```python
# Sprawdź czy monitoring działa
await energy_manager.start_monitoring()

# Obniż progi
energy_manager.cpu_threshold = 0.5  # 50%
```

### Problem: Scenariusze są trywialne ("Hello World")
**Przyczyna**: Niski poziom złożoności lub uboga dokumentacja  
**Rozwiązanie**:
```bash
# Zwiększ złożoność
DREAMING_SCENARIO_COMPLEXITY=complex

# Dodaj więcej wiedzy do GraphRAG
oracle_agent.ingest_file("path/to/advanced_docs.pdf")
```

## API Reference

### DreamEngine

#### `enter_rem_phase(max_scenarios, difficulty) -> Dict`
Rozpoczyna fazę REM - główna funkcja śnienia.

**Args:**
- `max_scenarios` (int): Maksymalna liczba scenariuszy (default: SETTINGS)
- `difficulty` (str): 'simple', 'medium', 'complex' (default: SETTINGS)

**Returns:**
```python
{
    "session_id": str,
    "status": "completed" | "interrupted" | "error" | "no_knowledge",
    "duration_seconds": float,
    "dreams_attempted": int,
    "dreams_successful": int,
    "success_rate": float
}
```

#### `get_statistics() -> Dict`
Zwraca statystyki DreamEngine.

### ScenarioWeaver

#### `weave_scenario(knowledge_fragment, difficulty, libraries) -> ScenarioSpec`
Generuje pojedynczy scenariusz.

**Args:**
- `knowledge_fragment` (str): Fragment dokumentacji/wiedzy
- `difficulty` (str, optional): Poziom trudności
- `libraries` (List[str], optional): Lista bibliotek do użycia

**Returns:** `ScenarioSpec` object

#### `weave_multiple_scenarios(knowledge_fragments, count, difficulty) -> List[ScenarioSpec]`
Generuje wiele scenariuszy.

### EnergyManager

#### `get_metrics() -> SystemMetrics`
Pobiera aktualne metryki systemu (CPU, RAM, temperatura).

#### `is_system_busy() -> bool`
Sprawdza czy system przekroczył progi zasobów.

#### `is_idle(threshold_minutes) -> bool`
Sprawdza czy system jest bezczynny.

#### `wake_up() -> None`
Natychmiastowo przerywa śnienie (callback dla wysokiego obciążenia).

#### `start_monitoring() / stop_monitoring() -> None`
Uruchamia/zatrzymuje monitoring zasobów w tle.

## Roadmap

### Planowane funkcje

1. **Docker Isolation** (v2)
   - Osobne namespace'y dla snów (`venom-dream-worker-X`)
   - Automatyczne czyszczenie kontenerów po sesji

2. **Dashboard "Dream Journal"** (v2)
   - Sekcja w The Academy
   - Statystyki nocy: "Wyśniłem 42 rozwiązania"
   - Możliwość ręcznego zatwierdzania snów

3. **Multi-Library Scenarios** (v2)
   - Łączenie 2+ bibliotek w jednym scenariuszu
   - Realityczne integracje (np. FastAPI + SQLAlchemy + Redis)

4. **Adaptive Difficulty** (v3)
   - Automatyczne dostosowanie złożoności na podstawie success rate
   - Progresywne uczenie (start: simple → medium → complex)

5. **Dream Replay** (v3)
   - Ponowne wykonanie zapisanych snów dla regresji
   - Benchmark scenariuszy na nowych wersjach bibliotek

## Przykłady Użycia

### Przykład 1: Nocna Sesja Śnienia

```python
# main.py - inicjalizacja systemu
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.memory.graph_rag_service import GraphRAGService
from venom_core.memory.lessons_store import LessonsStore
from venom_core.core.energy_manager import EnergyManager
from venom_core.core.dream_engine import DreamEngine
from venom_core.core.scheduler import BackgroundScheduler

# Build kernel
kernel = KernelBuilder().build()

# Inicjalizuj komponenty
graph_rag = GraphRAGService()
lessons_store = LessonsStore()
energy_manager = EnergyManager()

# Dream Engine
dream_engine = DreamEngine(
    kernel=kernel,
    graph_rag=graph_rag,
    lessons_store=lessons_store,
    energy_manager=energy_manager
)

# Scheduler
scheduler = BackgroundScheduler()
await scheduler.start()

# Zaplanuj nocne śnienie (2:00)
scheduler.schedule_nightly_dreaming(dream_engine, start_hour=2)

# Uruchom aplikację
await run_app()
```

### Przykład 2: Analiza Wyników

```python
# analyze_dreams.py
from pathlib import Path
import json

output_dir = Path("./data/synthetic_training")

# Statystyki
dream_files = list(output_dir.glob("dream_*.json"))
print(f"Total dreams: {len(dream_files)}")

# Analiza po bibliotekach
libraries_count = {}
for dream_file in dream_files:
    with open(dream_file) as f:
        data = json.load(f)
        for lib in data["scenario"]["libraries"]:
            libraries_count[lib] = libraries_count.get(lib, 0) + 1

print("\nMost practiced libraries:")
for lib, count in sorted(libraries_count.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"  {lib}: {count}")
```

## Wnioski

THE DREAMER to potężne narzędzie do self-improvement Venoma. Kluczowe zalety:

✅ **Automatyczne uczenie** - brak potrzeby manualnego tworzenia przykładów  
✅ **High quality data** - Guardian zapewnia 100% jakość  
✅ **Niewymagające zasobów** - działa w tle, niski priorytet  
✅ **Inteligentne przerwanie** - natychmiastowa reakcja na aktywność użytkownika  
✅ **Skalowalność** - od prostych do złożonych scenariuszy  

Pamiętaj: Im bogatszy Graf Wiedzy (GraphRAG), tym lepsze sny! 🌙
