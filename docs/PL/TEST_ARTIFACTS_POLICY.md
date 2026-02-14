# Polityka Artefaktów Testowych: CLEAN vs PRESERVE

## Przegląd

Niniejsza polityka definiuje ujednolicone podejście do zarządzania artefaktami testowymi w repozytorium Venom. Celem jest zapobieganie zanieczyszczeniu katalogów runtime przez testy przy jednoczesnym zachowaniu możliwości diagnostycznych.

## Tryby Działania

### Tryb CLEAN (Domyślny)

**Cel**: Utrzymanie czystego środowiska runtime po testach

**Zachowanie**:
- Artefakty testowe są zapisywane w izolowanych katalogach tymczasowych
- Wszystkie dane testowe są automatycznie usuwane po zakończeniu testów
- Katalogi runtime (`data/*`, `logs/*`) pozostają niezanieczyszczone
- Odpowiedni dla pipeline'ów CI/CD i lokalnego developmentu

**Kiedy używać**:
- Regularne testowanie lokalne (`make test`)
- Pipeline'y CI/CD (zawsze)
- Walidacja pre-commit/pre-push
- Walidacja bramek jakości

### Tryb PRESERVE (Opt-in)

**Cel**: Zachowanie artefaktów testowych do debugowania i analizy

**Zachowanie**:
- Artefakty testowe są zapisywane w katalogach trwałych
- Artefakty pozostają dostępne po zakończeniu testów
- Lokalizacja artefaktów jest logowana dla łatwego dostępu
- Odpowiedni dla debugowania błędów testowych lub analizy zachowania

**Kiedy używać**:
- Debugowanie nie przechodzących testów
- Analiza zachowania testów
- Rozwój nowych scenariuszy testowych
- Badanie przypadków brzegowych

## Zmienne Środowiskowe

### `VENOM_TEST_ARTIFACT_MODE`

Kontroluje strategię zachowania artefaktów.

**Wartości**:
- `clean` (domyślnie): Usuń artefakty po testach
- `preserve`: Zachowaj artefakty do analizy

**Przykłady**:
```bash
# Domyślny tryb CLEAN
make test

# Jawny tryb CLEAN
VENOM_TEST_ARTIFACT_MODE=clean make test

# Tryb PRESERVE
VENOM_TEST_ARTIFACT_MODE=preserve make test
```

### `VENOM_TEST_ARTIFACT_DIR`

Nadpisuje domyślną lokalizację katalogu artefaktów.

**Domyślnie**: `test-results/tmp/session-{timestamp}`

**Przykład**:
```bash
VENOM_TEST_ARTIFACT_DIR=/tmp/my-test-artifacts make test
```

## Struktura Katalogów Artefaktów

```
test-results/
└── tmp/
    └── session-{timestamp}/
        ├── timelines/          # Snapshoty timeline Chronos
        ├── synthetic_training/ # Outputy Dream Engine
        ├── training/           # Artefakty treningu Academy
        ├── logs/               # Logi specyficzne dla testów
        └── metadata.json       # Metadane sesji
```

## Wytyczne Implementacji Testów

### Używanie Fixture Artefaktów

Testy powinny używać fixture `test_artifact_dir` dla wszystkich ścieżek artefaktów:

```python
def test_creates_artifacts(test_artifact_dir):
    """Test tworzący artefakty w izolowanym katalogu."""
    output_file = test_artifact_dir / "output.json"
    output_file.write_text('{"test": "data"}')
    assert output_file.exists()
```

### Ścieżki Specyficzne dla Środowiska

Dla testów wymagających specyficznych ścieżek środowiskowych (timelines, training, itp.), użyj prekonfigurowanych zmiennych środowiskowych:

```python
def test_chronos_timeline():
    """Test używający CHRONOS_TIMELINES_DIR ustawionego w conftest.py."""
    # CHRONOS_TIMELINES_DIR jest już przekierowany do katalogu artefaktów testowych
    from venom_core.config import SETTINGS
    timeline_dir = Path(SETTINGS.CHRONOS_TIMELINES_DIR)
    # Artefakty zapisane tutaj będą zarządzane przez tryb artefaktów
```

### Oznaczanie Artefaktów Testowych

Artefakty testowe powinny być oznaczone metadanymi w celu identyfikacji:

```json
{
  "type": "test_artifact",
  "test_name": "test_example",
  "session_id": "session-20260214-191230",
  "timestamp": "2026-02-14T19:12:30Z"
}
```

## Targety Make

### `make test`

Uruchamia testy w trybie CLEAN (domyślnie).

```bash
make test
```

Równoważne:
```bash
VENOM_TEST_ARTIFACT_MODE=clean pytest
```

### `make test-data`

Uruchamia testy w trybie PRESERVE do debugowania.

```bash
make test-data
```

Równoważne:
```bash
VENOM_TEST_ARTIFACT_MODE=preserve pytest
```

Po zakończeniu wyświetla lokalizację artefaktów:
```
✅ Testy zakończone
📁 Artefakty zachowane w: test-results/tmp/session-20260214-191230
```

### `make test-artifacts-cleanup`

Ręcznie usuwa stare artefakty testowe.

```bash
# Usuń artefakty starsze niż 7 dni
make test-artifacts-cleanup

# Usuń wszystkie artefakty
make test-artifacts-cleanup CLEANUP_ALL=1
```

## Integracja CI/CD

Pipeline'y CI **zawsze** używają trybu CLEAN, aby zapobiec gromadzeniu artefaktów:

```yaml
- name: Run tests
  run: make test
  env:
    VENOM_TEST_ARTIFACT_MODE: clean
```

## Ochrona Katalogów Runtime

Następujące katalogi są chronione przed zanieczyszczeniem testowym:

- `data/timelines/` - Checkpointy Chronos
- `data/synthetic_training/` - Outputy Dream Engine
- `data/training/` - Dane treningowe Academy
- `logs/` - Logi aplikacji
- `workspace/` - Workspace'y użytkownika

Testy zapisujące do tych katalogów będą automatycznie przekierowywane do katalogu artefaktów testowych.

## Strategia Czyszczenia Artefaktów

### Tryb CLEAN
- Artefakty usuwane natychmiast po zakończeniu sesji testowej
- Używa pytest `autouse` fixtures do automatycznego czyszczenia
- Katalogi tymczasowe w pełni usuwane
- Nie wymaga ręcznej interwencji

### Tryb PRESERVE
- Artefakty pozostają w `test-results/tmp/session-{timestamp}/`
- Stare sesje nie są automatycznie usuwane
- Ręczne czyszczenie przez `make test-artifacts-cleanup` gdy potrzebne
- Czyszczenie oparte na TTL (domyślnie 7 dni) dla starych artefaktów

## Wykluczenia i Filtry

### Filtrowanie w Panelu/UI

Artefakty testowe są wykluczane z paneli operacyjnych:
- Widoki list timeline'ów filtrują artefakty testowe
- Listy jobów treningowych wykluczają sesje testowe
- Metryki dashboardu ignorują dane testowe

### Implementacja Filtra

```python
def is_test_artifact(metadata: dict) -> bool:
    """Sprawdza czy artefakt pochodzi z sesji testowej."""
    return (
        metadata.get("type") == "test_artifact"
        or metadata.get("session_id", "").startswith("test_")
    )
```

## Rozwiązywanie Problemów

### Testy zanieczyszczają katalogi runtime

**Objaw**: Dane testowe pojawiają się w `data/timelines/`, `data/training/`, itp.

**Rozwiązanie**:
1. Sprawdź czy test używa odpowiednich fixture (`test_artifact_dir`)
2. Sprawdź czy `tests/conftest.py` jest ładowany
3. Upewnij się że zmienne środowiskowe są poprawnie ustawione

### Artefakty nie są zachowywane w trybie PRESERVE

**Objaw**: Artefakty są usuwane nawet z `VENOM_TEST_ARTIFACT_MODE=preserve`

**Rozwiązanie**:
1. Zweryfikuj ustawienie zmiennej środowiskowej: `echo $VENOM_TEST_ARTIFACT_MODE`
2. Sprawdź implementację fixture w `tests/conftest.py`
3. Przejrzyj logikę czyszczenia testów

### Stare artefakty zajmują miejsce na dysku

**Objaw**: Katalog `test-results/tmp/` rośnie

**Rozwiązanie**:
```bash
# Usuń artefakty starsze niż 7 dni
make test-artifacts-cleanup

# Usuń wszystkie artefakty
make test-artifacts-cleanup CLEANUP_ALL=1
```

## Przewodnik Migracji

### Dla Istniejących Testów

1. **Testy używające `tmp_path`**: Nie wymagają zmian, już izolowane
2. **Testy zapisujące do `data/*`**: Zweryfikuj przekierowanie zmiennych środowiskowych w `conftest.py`
3. **Testy z własnym czyszczeniem**: Można usunąć ręczne czyszczenie, obsługiwane przez fixture

### Przykład Migracji

**Przed**:
```python
def test_example():
    output_dir = Path("data/training")
    output_dir.mkdir(parents=True, exist_ok=True)
    # ... logika testu ...
    # Ręczne czyszczenie
    shutil.rmtree(output_dir)
```

**Po**:
```python
def test_example(test_artifact_dir):
    # Środowisko już przekierowane, lub użyj fixture bezpośrednio
    output_dir = test_artifact_dir / "training"
    output_dir.mkdir(parents=True, exist_ok=True)
    # ... logika testu ...
    # Automatyczne czyszczenie obsługiwane przez fixture
```

## Bramki Jakości

Testy są uznawane za zgodne gdy:

1. ✅ `make test` kończy się bez zanieczyszczania katalogów runtime
2. ✅ Brak nowych wpisów w `data/timelines/`, `data/training/`, `logs/` po teście
3. ✅ `make pr-fast` przechodzi
4. ✅ `make check-new-code-coverage` przechodzi
5. ✅ Artefakty testowe prawidłowo oznaczone metadanymi
6. ✅ Tryb PRESERVE zachowuje artefakty z zalogowanymi poprawnymi ścieżkami

## Odniesienia

- Polityka Testowania: `docs/TESTING_POLICY.md`
- Polityka Bezpieczeństwa: `docs/SECURITY_POLICY.md`
- Wytyczne Agentów: `docs/AGENTS.md`
