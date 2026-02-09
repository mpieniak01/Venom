# Polityka testów

Ten dokument jest jednym, nadrzędnym źródłem zasad uruchamiania testów, bramek pokrycia i oczekiwań CI.

## Cele

- Szybki feedback lokalnie przed otwarciem PR.
- Stabilne pokrycie „new code” dla Sonara.
- Brak duplikacji instrukcji testowych w wielu dokumentach.

## Lokalne punkty wejścia testów

### Szybki smoke

```bash
source .venv/bin/activate || true
pytest -q
```

### Pełna suita backendu (domyślna ścieżka projektu)

```bash
make pytest
```

### Frontend

```bash
npm --prefix web-next run lint
npm --prefix web-next run build
npm --prefix web-next run test:e2e
```

## Lokalny pre-check pod Sonar

### Generowanie raportów Sonar

```bash
make sonar-reports
```

Artefakty:

- `test-results/sonar/python-coverage.xml`
- `test-results/sonar/python-junit.xml`
- `web-next/coverage/lcov.info`

### Lekki raport pokrycia backendu pod new code

```bash
make test-light-coverage
```

Przydatne opcje:

- `NEW_CODE_COVERAGE_MIN=70`
- `NEW_CODE_COV_TARGET=venom_core/execution/skills`
- `NEW_CODE_INCLUDE_BASELINE=0`

### Bramka pokrycia zmienionych linii (zalecane przed każdym PR)

```bash
make check-new-code-coverage
```

Domyślnie:

- baza diff: `origin/main`
- minimalne pokrycie zmienionych linii: `70%`

Przydatne opcje:

```bash
NEW_CODE_CHANGED_LINES_MIN=80 make check-new-code-coverage
NEW_CODE_DIFF_BASE=origin/main make check-new-code-coverage
```

## Performance i latency

Szczegółowe scenariusze i oczekiwane wartości:

- `docs/PL/TESTING_CHAT_LATENCY.md`

Główne komendy:

- `npm --prefix web-next run test:perf`
- `pytest tests/perf/test_chat_pipeline.py -m performance`
- `./scripts/run-locust.sh`

## CI i bramki PR

Wymagane bramki jakości na PR:

- CI Lite (szybki lint + wybrane testy unit)
- SonarCloud (bugi, podatności, utrzymywalność, duplikacje)

Oczekiwane lokalne checki przed PR:

1. `pre-commit run --all-files`
2. `mypy venom_core`
3. `make check-new-code-coverage`

## Najkrótszy proces wydania na PR

Użyj jednej komendy:

```bash
make pr-fast
```

Co robi:

- Wykrywa zmienione pliki względem `origin/main` (lub `PR_BASE_REF`).
- Uruchamia backend fast lane tylko gdy zmieniono backend.
- Uruchamia frontend fast lane tylko gdy zmieniono `web-next/**`.
- Dla zmian wyłącznie dokumentacyjnych pomija lane testowe.

Backend fast lane:

- `python3 -m compileall -q venom_core scripts tests`
- `make audit-ci-lite`
- `make check-new-code-coverage` (na grupach CI-lite + sonar-new-code)

Frontend fast lane:

- `npm --prefix web-next run lint`
- `npm --prefix web-next run test:unit:ci-lite`

Opcjonalna zmiana bazy diff:

```bash
PR_BASE_REF=origin/main make pr-fast
```

## Polityka artefaktów testowych

Nie commitujemy artefaktów wyników testów.

Ignorowane wg polityki:

- `**/test-results/`
- `perf-artifacts/`
- `playwright-report/`
- lokalne artefakty Sonar generowane przez `make sonar-reports`
