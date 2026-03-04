# Przewodnik Architektury Sonar

Ten dokument opisuje, jak Venom konfiguruje analizę architektury dla Sonar.

## Cele

1. Utrzymać zgodność bramek architektonicznych ze standardowym workflow Sonar.
2. Trzymać model architektury w repozytorium (wersjonowanie + review).
3. Unikać dublowania bramek architektury.

## Pliki konfiguracyjne

1. Guard importów Python:
   - `config/architecture/contracts.yaml`
   - walidowany przez `scripts/check_architecture_contracts.py`
2. Model architektury Sonar:
   - `config/architecture/sonar-architecture.yaml`
   - walidowany przez `scripts/validate_sonar_architecture.py`

## Walidacja lokalna

Uruchom istniejącą bramkę architektury:

```bash
make architecture-drift-check
```

Komenda sprawdza:
1. kontrakty importów (`venom_core`),
2. strukturę pliku architektury Sonar.

Opcjonalny eksport podsumowania do ręcznej synchronizacji UI Sonar:

```bash
make architecture-sonar-export
```

Wynik:
1. `test-results/sonar/architecture-summary.json`

## Integracja z Sonar

Venom przekazuje ścieżkę pliku architektury przez:

```properties
sonar.architecture.configpath=./config/architecture/sonar-architecture.yaml
```

Właściwość jest ustawiona w `sonar-project.properties`.

### Opcjonalne tryby uruchomień Sonar

Jawne wskazanie pliku:

```bash
mvn clean verify sonar:sonar -Dsonar.architecture.configpath=./config/architecture/sonar-architecture.yaml
```

Uruchomienie bez pliku (porównanie/diagnostyka):

```bash
mvn clean verify sonar:sonar -Dsonar.architecture.noconfig
```

## Workflow aktualizacji

1. Zaktualizuj `config/architecture/sonar-architecture.yaml`.
2. Uruchom `make architecture-drift-check`.
3. Uruchom `make pr-fast`.
4. Zsynchronizuj ten sam model w Sonar Intended Architecture UI (podejście Sonar-first).

## Uwagi

1. Utrzymuj jeden aktywny plik architektury na przebieg analizy.
2. Nie dodawaj równoległej, konfliktowej bramki architektury.
