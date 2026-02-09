# Polityka testów

Ten dokument jest nadrzędnym źródłem zasad testowania: od codziennej pracy lokalnej, przez gotowość do PR, po walidację pod wydanie.

## Drabina testów (od najszybszych do najbardziej restrykcyjnych)

### Poziom 1: Codzienna praca lokalna (codziennie)

Cel: bardzo szybki feedback w trakcie implementacji.

Uruchom:

```bash
source .venv/bin/activate || true
pytest -q
```

Gdy zmieniasz frontend, dodaj:

```bash
npm --prefix web-next run lint
```

### Poziom 2: Gałąź gotowa do PR (obowiązkowo przed push)

Cel: szybka walidacja zbliżona do bramek PR.

Uruchom jedną komendę:

```bash
make pr-fast
```

Zakres:

- wykrywanie zmienionych plików względem `origin/main` (lub `PR_BASE_REF`)
- backend fast lane: compile check + audit CI-lite + bramka pokrycia zmienionych linii
- frontend fast lane (tylko gdy zmieniono `web-next/**`): lint + unit CI-lite

### Poziom 3: Jakość pod PR (obowiązkowo przed merge)

Cel: zgodność z wymaganiami CI i Sonar.

Wymagane checki:

1. `pre-commit run --all-files`
2. `mypy venom_core`
3. `make check-new-code-coverage`

Domyślna bramka pokrycia:

- baza diff: `origin/main`
- minimalne pokrycie zmienionych linii: `70%`

Przydatne opcje:

```bash
NEW_CODE_CHANGED_LINES_MIN=80 make check-new-code-coverage
NEW_CODE_DIFF_BASE=origin/main make check-new-code-coverage
```

### Poziom 4: Walidacja pod wydanie (gdy potrzebna)

Cel: wyższa pewność dla większych zmian lub przed release.

Backend:

```bash
make pytest
```

Frontend:

```bash
npm --prefix web-next run build
npm --prefix web-next run test:e2e
```

Pakiet raportów Sonar:

```bash
make sonar-reports
```

Artefakty:

- `test-results/sonar/python-coverage.xml`
- `test-results/sonar/python-junit.xml`
- `web-next/coverage/lcov.info`

Scenariusze performance/latency:

- `docs/PL/TESTING_CHAT_LATENCY.md`
- `npm --prefix web-next run test:perf`
- `pytest tests/perf/test_chat_pipeline.py -m performance`
- `./scripts/run-locust.sh`

## CI i Sonar (referencja)

Wymagane bramki na PR:

- CI Lite (szybki lint + wybrane testy unit)
- SonarCloud (bugi, podatności, utrzymywalność, duplikacje)

## Polityka artefaktów testowych

Nie commitujemy artefaktów wyników testów.

Ignorowane wg polityki:

- `**/test-results/`
- `perf-artifacts/`
- `playwright-report/`
- lokalne artefakty Sonar generowane przez `make sonar-reports`
