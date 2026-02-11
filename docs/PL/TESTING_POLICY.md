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

Upewnij się, że hooki są zainstalowane dla `pre-commit` i `pre-push`:

```bash
make install-hooks
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
- minimalne pokrycie zmienionych linii: `80%`

Przydatne opcje:

```bash
NEW_CODE_CHANGED_LINES_MIN=80 make check-new-code-coverage
NEW_CODE_DIFF_BASE=origin/main make check-new-code-coverage
NEW_CODE_AUTO_INCLUDE_CHANGED=1 make check-new-code-coverage
```

Zachowanie runu new-code coverage:

- bazowe grupy testów: `config/pytest-groups/ci-lite.txt` + `config/pytest-groups/sonar-new-code.txt`
- automatyczne dołączanie testów zmienionych/powiązanych jest domyślnie aktywne (`NEW_CODE_AUTO_INCLUDE_CHANGED=1`)
- wzorzec auto-include dla zmienionych testów: `tests/**/test_*.py`
- resolver listy: `scripts/resolve_sonar_new_code_tests.py`
- gdy lokalnie nie ma `ripgrep` (`rg`), resolver używa fallbacku Python (bez blokowania runu)
- w CI backend-lite doinstalowuje `ripgrep` dla szybszego wyboru i czytelnych logów

### Poziom 4: Walidacja pod wydanie (gdy potrzebna)

Cel: wyższa pewność dla większych zmian lub przed release.

Backend:

```bash
make pytest
```

`make pytest` uruchamia grupy backendu w kolejności: `heavy` -> `long` -> `fast`.

Frontend:

```bash

```

Pakiet raportów Sonar:

```bash
make sonar-reports
```

Artefakty:

- `test-results/sonar/python-coverage.xml`
- `test-results/sonar/python-junit.xml`
- `web-next/coverage/lcov.info` (artefakt opcjonalny/lokalny; tymczasowo nieużywany w bramce coverage Sonara)

Scenariusze performance/latency:

- `docs/PL/TESTING_CHAT_LATENCY.md`
- `npm --prefix web-next run test:perf`
- `pytest tests/perf/test_chat_pipeline.py -m performance`
- `./scripts/run-locust.sh`

## CI i Sonar (referencja)

Wymagane bramki na PR:

- CI Lite (szybki lint + wybrane testy unit)
- SonarCloud (bugi, podatności, utrzymywalność, duplikacje)
- Wyjątek tymczasowy: frontend `web-next/**` jest wyłączony z bramki Sonar coverage do czasu stabilizacji UI.

## Kryteria jakości i typowe obszary wpadek

To są najczęściej powracające problemy jakościowe w repo i wskaźniki, którymi je mierzymy.

### 1) Błędy bezpieczeństwa

Typowe wpadki:

- logowanie danych sterowanych przez użytkownika w route'ach backendu
- regexy podatne na backtracking (DoS)
- nieprzejrzane Security Hotspots w Sonar

Wskaźniki:

- Sonar `Security Hotspots Reviewed`: cel `100%` w zakresie PR
- Sonar `Vulnerabilities` i `Bugs`: brak nowych `Critical/High`

### 2) Kod spaghetti / zbyt złożone ścieżki

Typowe wpadki:

- wysoka złożoność kognitywna (`brain-overload`)
- długie drzewa warunków w route'ach i orkiestracji
- mieszanie walidacji, logiki i mapowania odpowiedzi w jednej funkcji

Wskaźniki:

- Python complexity check: `ruff check venom_core --select C901`
- próg Sonar dla Cognitive Complexity na funkcję: `<= 15`
- brak nowych `Critical` maintainability w zakresie PR

### 3) Zbyt głębokie zagnieżdżenia

Typowe wpadki:

- głęboko zagnieżdżone bloki/callbacki obniżające czytelność i testowalność

Wskaźniki:

- brak nowych otwartych issue Sonar o nadmiernym zagnieżdżeniu w zakresie PR
- preferowanie guard clauses / early return przy refaktorze

### 4) Słabe pokrycie new code

Typowe wpadki:

- testy przechodzą, ale zmienione linie są niepokryte
- nowe testy nie trafiają do lekkiej grupy Sonar

Wskaźniki:

- lokalna bramka changed-lines: `make check-new-code-coverage`
- minimalny próg wymuszony: `NEW_CODE_CHANGED_LINES_MIN=80` (domyślnie)
- rekomendowany bufor przed push: `>= 80%`
- referencyjna gałąź Sonar dla new-code: `main` (`sonar.newCode.referenceBranch=main`)

### 5) Rozjazd optional dependencies w CI-lite

Typowe wpadki:

- test importuje opcjonalną paczkę, której nie ma w środowisku CI-lite
- brak paczki kończy się `ERROR`/`FAILED` zamiast jawnego `skipped`
- nowy test trafia do runu bez zdefiniowanej polityki zależności

Wskaźniki:

- testy z opcjonalną biblioteką używają `pytest.importorskip(...)`, jeśli dependency nie jest obowiązkowe dla CI-lite
- lekkie zależności systemowe pomocne dla szybkich bramek (np. `ripgrep`) są instalowane w jobie CI-lite
- backend-lite pokazuje jawne `skipped` (a nie import error) dla testów optional-dependency

## Polityka artefaktów testowych

Nie commitujemy artefaktów wyników testów.

Ignorowane wg polityki:

- `**/test-results/`
- `perf-artifacts/`
- `playwright-report/`
- lokalne artefakty Sonar generowane przez `make sonar-reports`

## Definition of Done (bramki jakości)

Zmiana jest `Done` dopiero po przejściu wszystkich bramek dla zakresu PR:

1. Szybka bramka PR lokalnie:
   - `make pr-fast`
2. Statyczna jakość:
   - `pre-commit run --all-files`
   - `mypy venom_core`
   - `ruff check venom_core --select C901` (brak naruszeń złożoności w zmienionym zakresie)
3. Bramka pokrycia new code:
   - `make check-new-code-coverage`
   - changed-lines coverage `>= 80%`
4. Bramka SonarCloud na PR:
   - brak nowych `Critical/High` bugów/podatności
   - brak nowych otwartych blockerów maintainability w zakresie PR
   - Security Hotspots w zakresie PR przejrzane (`100%`)
5. Gdy zmieniasz frontend:
   - `npm --prefix web-next run lint`
   - `npm --prefix web-next run test:unit:ci-lite`

## Polityka Optional Dependencies (CI-lite)

Stosuj poniższą regułę dla testów uruchamianych przez `make check-new-code-coverage`:

1. Doinstaluj paczkę w CI-lite, gdy jest lekka i szeroko przydatna dla szybkich bramek.
2. Użyj `pytest.importorskip("package")`, gdy paczka jest ciężka, środowiskowa lub opcjonalna z założenia.
3. Brak opcjonalnej paczki nie może wywracać backend-lite surowym import error.

Przykłady aktualnie egzekwowane:

- `tests/test_mcp_manager.py` używa `pytest.importorskip("mcp")`
- `tests/test_model_discovery.py` używa `pytest.importorskip("bs4")` w ścieżce scrapingowej
- job backend-lite instaluje `ripgrep` dla `scripts/resolve_sonar_new_code_tests.py`
