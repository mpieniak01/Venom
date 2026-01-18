# THE_CHRONOMANCER - Przewodnik Systemu Zarządzania Stanem

## 📖 Wprowadzenie

**The Chronomancer** (Zarządca Czasu) to zaawansowany system zarządzania stanem i liniami czasowymi w projekcie Venom. Umożliwia tworzenie snapshotów całego stanu systemu (kod + pamięć + konfiguracja), eksperymentowanie na oddzielnych liniach czasowych oraz bezpieczne przywracanie do wcześniejszych punktów w przypadku błędów.

## 🎯 Główne Funkcjonalności

### 1. Checkpointy (Punkty Przywracania)
- **Tworzenie migawek** całego stanu systemu
- **Przywracanie** do dowolnego punktu w historii
- **Zarządzanie** wieloma punktami przywracania
- **Automatyczne backupy** przed ryzykownymi operacjami

### 2. Linie Czasowe (Timeline Branching)
- **Tworzenie** oddzielnych linii czasowych do eksperymentowania
- **Izolacja** eksperymentów od głównego projektu
- **Bezpieczne testowanie** ryzykownych zmian
- **Historia** wszystkich zmian i decyzji

### 3. Zarządzanie Ryzykiem
- **Automatyczna ocena** ryzyka operacji
- **Rekomendacje** tworzenia checkpointów
- **Analiza błędów** i uczenie się na podstawie niepowodzeń
- **Integracja z LessonsStore** do zapisywania doświadczeń

## 🏗️ Architektura

System składa się z trzech głównych komponentów:

```
┌─────────────────────────────────────────────────────────┐
│                    THE_CHRONOMANCER                      │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Chronos    │  │  Historian   │  │  ChronoSkill │  │
│  │   Engine     │◄─┤    Agent     │◄─┤              │  │
│  │              │  │              │  │              │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘  │
│         │                 │                              │
│         │                 │                              │
│         ▼                 ▼                              │
│  ┌──────────────┐  ┌──────────────┐                    │
│  │  Snapshots   │  │    Lessons   │                    │
│  │  (Git+DB)    │  │     Store    │                    │
│  └──────────────┘  └──────────────┘                    │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

### ChronosEngine
Rdzeń systemu - zarządza tworzeniem i przywracaniem migawek.

**Kluczowe metody:**
- `create_checkpoint(name, description, timeline)` - tworzy snapshot
- `restore_checkpoint(id, timeline)` - przywraca stan
- `list_checkpoints(timeline)` - lista snapshotów
- `create_timeline(name)` - nowa linia czasowa
- `delete_checkpoint(id)` - usuwa snapshot

**Struktura Snapshotu:**
```
data/timelines/{timeline}/{checkpoint_id}/
├── checkpoint.json        # Metadane
├── fs_diff.patch         # Różnice w kodzie (Git)
├── git_status.txt        # Status Git
├── memory_dump/          # Backup baz danych
│   ├── test.db
│   └── vector_store/
└── env_config.json       # Konfiguracja środowiska
```

### HistorianAgent
Agent odpowiedzialny za zarządzanie ryzykiem i analizę przyczynową.

**Główne funkcje:**
- Ocena ryzyka operacji (niskie/średnie/wysokie)
- Rekomendacja checkpointów przed ryzykownymi akcjami
- Analiza błędów i zapisywanie lekcji
- Zarządzanie historią zmian

**Poziomy ryzyka:**
- 🟢 **Niskie**: Operacje tylko do odczytu
- 🟡 **Średnie**: Modyfikacje, aktualizacje
- 🔴 **Wysokie**: hot_patch, delete, refactor, migration

### ChronoSkill
Interfejs Semantic Kernel dla agentów do interakcji z systemem.

**Dostępne funkcje kernel:**
- `create_checkpoint(name, description, timeline)`
- `restore_checkpoint(checkpoint_id, timeline)`
- `list_checkpoints(timeline)`
- `delete_checkpoint(checkpoint_id, timeline)`
- `branch_timeline(name)`
- `list_timelines()`
- `merge_timeline(source, target)` - placeholder

## 🚀 Użycie

### Przykład 1: Podstawowe Użycie

```python
from venom_core.core.chronos import ChronosEngine

# Inicjalizacja
chronos = ChronosEngine()

# Utwórz checkpoint przed ryzykowną operacją
checkpoint_id = chronos.create_checkpoint(
    name="before_refactoring",
    description="Przed dużym refactoringiem modułu core"
)

# ... wykonaj operacje ...

# Jeśli coś poszło nie tak, przywróć
if error_occurred:
    chronos.restore_checkpoint(checkpoint_id)
```

### Przykład 2: Użycie HistorianAgent

```python
from semantic_kernel import Kernel
from venom_core.agents.historian import HistorianAgent

kernel = Kernel()
historian = HistorianAgent(kernel)

# Oceń ryzyko operacji
result = await historian.process("Wykonaj hot_patch na module core")
# Jeśli wysokie ryzyko, rekomenduje checkpoint

# Utwórz checkpoint bezpieczeństwa
checkpoint_id = historian.create_safety_checkpoint(
    name="pre_hotpatch",
    description="Przed zastosowaniem hot_patch"
)

# Po błędzie, analizuj i ucz się
await historian.analyze_failure(
    operation="hot_patch on core.py",
    error="SyntaxError: invalid syntax",
    checkpoint_before=checkpoint_id
)
```

### Przykład 3: Linie Czasowe dla Eksperymentów

```python
# Utwórz checkpoint na głównej linii
main_checkpoint = chronos.create_checkpoint(
    name="stable_state",
    timeline="main"
)

# Utwórz eksperymentalną timeline
chronos.create_timeline("experimental")

# Eksperymentuj na oddzielnej linii
exp_checkpoint = chronos.create_checkpoint(
    name="experiment_start",
    timeline="experimental"
)

# ... przeprowadź eksperymenty ...

# Jeśli sukces, wiedza jest już w LessonsStore
# Jeśli porażka, przywróć główną linię
chronos.restore_checkpoint(main_checkpoint, timeline="main")
```

### Przykład 4: Użycie przez Semantic Kernel

```python
from venom_core.execution.skills.chrono_skill import ChronoSkill

# Dodaj skill do kernela
chrono_skill = ChronoSkill()
kernel.add_plugin(chrono_skill, plugin_name="chronos")

# Agenci mogą teraz używać funkcji czasowych:
# - "Utwórz checkpoint przed rozpoczęciem"
# - "Przywróć checkpoint abc123"
# - "Pokaż listę checkpointów"
# - "Utwórz nową timeline eksperymentalną"
```

## 🔧 Konfiguracja

W pliku `config.py` dodano nowe ustawienia:

```python
# Konfiguracja THE_CHRONOMANCER
ENABLE_CHRONOS: bool = True
CHRONOS_TIMELINES_DIR: str = "./data/timelines"
CHRONOS_AUTO_CHECKPOINT: bool = True
CHRONOS_MAX_CHECKPOINTS_PER_TIMELINE: int = 50
CHRONOS_CHECKPOINT_RETENTION_DAYS: int = 30
CHRONOS_COMPRESS_SNAPSHOTS: bool = True
```

## 🔗 Integracja z DreamEngine [v2.0]

DreamEngine został zintegrowany z Chronos do bezpiecznego eksperymentowania:

```python
class DreamEngine:
    def __init__(self, ..., chronos_engine=None):
        self.chronos = chronos_engine or ChronosEngine()

    async def enter_rem_phase(self, ...):
        # Utwórz tymczasową timeline dla snów
        timeline_name = f"dream_{session_id}"
        self.chronos.create_timeline(timeline_name)

        # Utwórz checkpoint bezpieczeństwa
        checkpoint_id = self.chronos.create_checkpoint(
            name=f"dream_start_{session_id}",
            timeline=timeline_name
        )

        # ... śnij ...

        # Jeśli sukces (>50% sukcesów), zachowaj wiedzę
        # Jeśli porażka, timeline pozostaje jako historia
```

**Zalety:**
- Sny nie zaśmiecają głównej pamięci
- Każdy sen ma własną timeline
- Łatwe cofnięcie nieudanych eksperymentów
- Historia wszystkich prób dostępna do analizy

## 📊 Monitoring i Diagnostyka

### Sprawdzanie Stanu Systemu

```python
# Lista wszystkich linii czasowych
timelines = chronos.list_timelines()
print(f"Dostępne timelines: {timelines}")

# Lista checkpointów na timeline
checkpoints = chronos.list_checkpoints(timeline="main")
for cp in checkpoints:
    print(f"{cp.name} ({cp.checkpoint_id}) - {cp.timestamp}")

# Historia checkpointów (HistorianAgent)
history = historian.get_checkpoint_history(limit=10)
```

### Statystyki Snapshotów

```bash
# Rozmiar katalogów snapshotów
du -sh data/timelines/*

# Liczba checkpointów
find data/timelines -name "checkpoint.json" | wc -l
```

## 🛡️ Bezpieczeństwo

### Co Jest Zapisywane w Snapshots
- ✅ Git diff (zmiany w plikach)
- ✅ Status Git (uncommitted files)
- ✅ Backup baz danych (LanceDB, GraphStore)
- ✅ Konfiguracja środowiska (bez sekretów)

### Czego NIE Zapisujemy
- ❌ Sekretów i haseł (.env)
- ❌ Dużych plików binarnych (modele ML)
- ❌ Katalogu .git (używamy diff)
- ❌ Node_modules, venv, etc.

### Zalecenia
1. **Regularne czyszczenie** starych checkpointów
2. **Limity** liczby checkpointów per timeline
3. **Kompresja** snapshotów (jeśli włączona)
4. **Backup** ważnych checkpointów poza projekt

## 🧪 Testowanie

Utworzono kompleksowe testy:

```bash
# Testy jednostkowe
pytest tests/test_chronos.py -v
pytest tests/test_historian_agent.py -v
pytest tests/test_chrono_skill.py -v

# Wszystkie testy Chronos
pytest tests/test_chrono*.py tests/test_historian*.py -v
```

**Pokrycie testów:**
- ✅ Tworzenie i przywracanie checkpointów
- ✅ Zarządzanie liniami czasowymi
- ✅ Ocena ryzyka operacji
- ✅ Analiza błędów i zapisywanie lekcji
- ✅ Integracja z LessonsStore
- ✅ Pełne cykle życia checkpointów

## 🔮 Przyszłe Rozszerzenia

### W Planach
1. **Inteligentne Merge** linii czasowych z konfliktami (przez LLM)
2. **Automatyczna kompresja** starych snapshotów
3. **Garbage Collection** nieużywanych checkpointów
4. **Dashboard** wizualizacji linii czasowych (Web UI)
5. **Git Worktree** dla fizycznej izolacji branchy
6. **Docker Volume Snapshots** dla pełnej izolacji kontenerów

### Zaawansowane Scenariusze
- **A/B Testing**: Dwie timelines, porównanie wyników
- **Chaos Engineering**: Testowanie odporności z automatycznym rollback
- **Training Pipelines**: Timeline per eksperyment treningowy
- **Production Rollback**: Szybkie cofnięcie deploymentu

## 📝 Best Practices

1. **Nazywaj checkpointy opisowo**: Zamiast "cp1" użyj "before_migration_v1"
2. **Dodawaj opisy**: Pomaga przy późniejszej analizie
3. **Twórz checkpointy przed ryzykownymi operacjami**: hot_patch, migrations, refactoring
4. **Używaj oddzielnych timelines do eksperymentów**: Nie zaśmiecaj main
5. **Regularnie czyść stare checkpointy**: Oszczędność miejsca
6. **Dokumentuj decyzje**: Dlaczego utworzyłeś checkpoint, co się zmieniło

## 🆘 Troubleshooting

### Problem: Checkpoint nie przywraca plików
**Rozwiązanie**: Sprawdź czy znajdujesz się w repozytorium Git. ChronosEngine używa `git diff` i `git apply`.

### Problem: Brak miejsca na dysku
**Rozwiązanie**:
1. Usuń stare checkpointy: `chronos.delete_checkpoint(id)`
2. Włącz kompresję: `CHRONOS_COMPRESS_SNAPSHOTS = True`
3. Zmniejsz limit: `CHRONOS_MAX_CHECKPOINTS_PER_TIMELINE = 10`

### Problem: Przywracanie checkpointu kończy się błędem
**Rozwiązanie**: Sprawdź logi. Możliwe przyczyny:
- Konflikty Git (ręcznie rozwiąż)
- Brak uprawnień do plików
- Usunięty katalog memory

### Problem: Historian nie rekomenduje checkpointów
**Rozwiązanie**: Sprawdź czy operacja zawiera słowa kluczowe wysokiego ryzyka (hot_patch, delete, migration). Możesz rozszerzyć listę w `historian.py`.

## 📚 Powiązane Dokumenty

- [THE_DREAMER](./DREAM_ENGINE_GUIDE.md) - Integracja z snami
- [THE_ACADEMY](./THE_ACADEMY.md) - Training pipelines
- [MEMORY_LAYER_GUIDE](./MEMORY_LAYER_GUIDE.md) - LessonsStore
- [GUARDIAN_GUIDE](./GUARDIAN_GUIDE.md) - Walidacja zmian

## 🎓 Przykład End-to-End

```python
# Scenariusz: Bezpieczna migracja bazy danych

# 1. Oceń ryzyko
historian = HistorianAgent(kernel)
risk_assessment = await historian.process(
    "Przeprowadź migrację schematu bazy danych"
)
# → Rekomenduje checkpoint (wysokie ryzyko)

# 2. Utwórz checkpoint bezpieczeństwa
checkpoint_id = historian.create_safety_checkpoint(
    name="pre_migration_v1",
    description="Przed migracją do wersji 2.0 schematu"
)

# 3. Wykonaj migrację
try:
    run_database_migration()
except Exception as e:
    # 4. Błąd - analizuj i cofnij
    await historian.analyze_failure(
        operation="database_migration_v1",
        error=str(e),
        checkpoint_before=checkpoint_id
    )

    # Przywróć checkpoint
    chronos.restore_checkpoint(checkpoint_id)
    logger.error("Migracja nie powiodła się, system przywrócony")
else:
    # 5. Sukces - zapisz nową lekcję
    lessons_store.add_lesson(
        situation="Migracja bazy danych do v1.0",
        action="Wykonano migrację z checkpointem bezpieczeństwa",
        result="SUKCES",
        feedback="Checkpoint umożliwił bezpieczne testowanie",
        tags=["migration", "database", "checkpoint"]
    )
```

---

**Autorzy**: Venom Core Team
**Wersja**: 1.0
**Data**: 2024-12-08
**Status**: Implemented ✅
