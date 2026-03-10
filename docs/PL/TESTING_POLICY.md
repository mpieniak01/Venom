# Polityka testów

Ten dokument jest nadrzędnym źródłem zasad testowania: od codziennej pracy lokalnej, przez gotowość do PR, po walidację pod wydanie.

Bazowe wymagania bezpieczeństwa i kontroli są opisane w `docs/PL/SECURITY_POLICY.md`.

## Drabina testów (od najszybszych do najbardziej restrykcyjnych)

### Poziom 1: Codzienna praca lokalna (codziennie)

Cel: bardzo szybki feedback w trakcie implementacji.

Przed dopisaniem nowych testów sprawdź, czy wymagane pakiety są dostępne w aktualnym środowisku oraz czy są zgodne z polityką zależności CI-lite.

Uruchom:

```bash
test -f .venv/bin/activate || { echo "Brak .venv/bin/activate. Najpierw utwórz .venv."; exit 1; }
source .venv/bin/activate
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

Niezależny check kontraktów architektury (również uruchamiany w `pr-fast`):

```bash
make architecture-drift-check
```

Niezależny check kontraktów lane'ów testowych (również uruchamiany w `pr-fast`):

```bash
make test-lane-contracts-check
```

Kanoniczny check taksonomii testów (również uruchamiany w `pr-fast`):

```bash
make test-catalog-check
```

Regeneracja kanonicznego katalogu po większych refaktorach/rename testów:

```bash
make test-catalog-sync
```

Synchronizacja plików grup pytest z katalogu:

```bash
make test-groups-sync
```

Weryfikacja, że grupy są zsynchronizowane (brak ręcznego dryfu):

```bash
make test-groups-check
```

Upewnij się, że hooki są zainstalowane dla `pre-commit` i `pre-push`:

```bash
make install-hooks
```

Zakres:

- wykrywanie zmienionych plików względem `origin/main` (lub `PR_BASE_REF`)
- backend fast lane: compile check + architecture drift guard + guard kontraktów lane'ów + guard katalogu testów + audit CI-lite + bramka pokrycia zmienionych linii
- frontend fast lane (tylko gdy zmieniono `web-next/**`): lint + unit CI-lite

Kontrakt nazewnictwa lane/group:

- `config/pytest-groups/fast.txt` jest kanoniczną listą szybkiego zakresu backendu.
- `config/pytest-groups/light.txt` jest aliasem kompatybilności do `fast.txt` i nie powinien być edytowany niezależnie.

Kontrakt architektoniczny routerów (backend):

- Routery `venom_core/api/routes/*` powinny być cienką warstwą HTTP i delegować logikę operacyjną do `venom_core/services/*`.
- Test `tests/test_api_routes_import_guard.py` blokuje nowy dryf warstwowy (`routes -> core/infrastructure`) oraz niekontrolowane importy efektów ubocznych.
- Przy dekompozycji routera dopisz testy dla nowego modułu service (gałęzie success/error/retry), aby utrzymać pokrycie zmian po ekstrakcji.

Minimalny kontrakt testów dla runtime selection (Chat + Models):

- backend: `tests/test_llm_runtime_activation_api.py` (aktywacja runtime + walidacja provider/model),
- backend: `tests/test_llm_runtime_options_api.py` (snapshot kontraktu `/api/v1/system/llm-runtime/options`),
- frontend: `web-next/tests/use-runtime.test.ts` (mapowanie opcji runtime/model po stronie panelu Models),
- frontend: `web-next/tests/chat-send-helpers.test.ts` (regresja przepływu wysyłki i przełączenia runtime).

Minimalny kontrakt testów dla Academy trainable models (PR 186):

- backend: `tests/test_academy_models_module.py` (klasyfikacja `source_type/cost_tier`, sortowanie `priority_bucket`, dynamiczna `runtime_compatibility`),
- backend: `tests/test_llm_runtime_options_api.py` (kontrakt `model_catalog.trainable_models` w `/api/v1/system/llm-runtime/options`),
- backend: `tests/test_academy_api_contracts.py` (guard aktywacji adaptera przy niekompatybilnym runtime),
- frontend: `web-next/tests/academy-training-picker.test.ts` (sekcje i kolejnosc pseudo-selecta: local -> cloud free -> cloud other),
- frontend: `web-next/tests/cockpit-i18n-and-inspector-utils.test.ts` + testy chat selectora (regresja komunikatow i blokad adapter/runtime).

Minimalny kontrakt Academy po 196:

- backend: `tests/test_academy_models_module.py` utrzymuje klasyfikację `model_catalog.trainable_models`, gating rodzin runtime i zasady kanonicznych metadanych adaptera,
- backend: `tests/test_academy_api_contracts.py` utrzymuje kontrakty end-to-end Academy (`training`, `self-learning`, aktywacja/dezaktywacja adaptera, structured errors),
- backend: `tests/test_academy_self_learning_routes.py` utrzymuje mapowanie błędów self-learning do `reason_code`,
- frontend: `web-next/tests/academy-training-picker.test.ts` i `web-next/tests/self-learning-ui.component.test.tsx` utrzymują jawną semantykę wyboru `server + model + base_model`,
- frontend: `web-next/tests/self-learning-panel-error.test.tsx` i `web-next/tests/academy-api.test.ts` utrzymują structured błędy w UI,
- frontend/browser: `web-next/tests/academy-smoke.spec.ts` utrzymuje kanoniczny flow `repo_readmes -> canonical adapter metadata -> activate -> chat`.

Zasady:

- testy nie mogą utrwalać fallbacku do `ACADEMY_DEFAULT_BASE_MODEL`, `LAST_MODEL_*` ani `LLM_MODEL_NAME` jako poprawnego zachowania Academy,
- adapter bez kanonicznego `metadata.json` jest nieważnym artefaktem i w testach powinien być reprezentowany jako stan blocked/removed, nie repairable,
- Chat, Training i Self-learning muszą wyprowadzać wybór runtime/modelu z `/api/v1/system/llm-runtime/options`, a nie z oddzielnych hardcodowanych fixture.

Kontrakt skip dla precondition środowiska (197B):

- Dla testów wymagających działających usług stan środowiska musi być klasyfikowany reason-code:
  - `stack_not_started`
  - `stack_degraded`
  - `runtime_model_unavailable`
- `stack_not_started` i `stack_degraded` oznaczają niespełniony precondition środowiska, a nie regresję produktu:
  - preflight E2E zwraca ścieżkę skip (stan diagnostyczny mapowany na skip),
  - funkcjonalne testy E2E wykonują skip, gdy runtime/model nie jest gotowy,
  - testy backendowe wymagające żywego stacka używają `@pytest.mark.requires_stack` i wykonują skip przy braku precondition.
- Czerwony test (`fail`) jest zarezerwowany dla regresji funkcjonalnej przy spełnionym precondition (`ready`).

Model taksonomii testów (źródło kanoniczne: `config/testing/test_catalog.json`):

- `domain`: zakres domenowy/systemowy (np. `academy`, `workflow`, `providers`, `runtime`)
- `test_type`: `unit`, `route_contract`, `service_contract`, `integration`, `perf`, `gate`
- `intent`: regression/contract/gate/security/performance
- `legacy_targeted`: historyczne testy typu PR-gate/coverage-wave; muszą mieć przypisaną domenę

Kontrakt jednego źródła prawdy:

- `config/testing/test_catalog.json` jest kanonicznym źródłem metadanych testów i uprawnień lane.
- `config/testing/test_catalog.yaml` pozostaje symlinkiem kompatybilności do `test_catalog.json` dla starszych narzędzi.
- Pliki grup pytest są generowane/synchronizowane z katalogu (`make test-groups-sync`).
- Ręczna edycja wygenerowanych grup nie jest wspierana; używaj komendy sync.

Przy dodawaniu nowego testu (`tests/**/test_*.py`) uruchom:

```bash
make test-catalog-sync
make test-groups-sync
make test-catalog-check
make pr-fast
```

### Poziom 3: Jakość pod PR (obowiązkowo przed merge)

Cel: zgodność z wymaganiami CI i Sonar.

Minimalny zestaw przed `PR-ready` (kopiuj 1:1):

```bash
pre-commit run --all-files
mypy venom_core
make check-new-code-coverage
```

Kontrakt bramek vs telemetrii:

- `make check-new-code-coverage` to gate blokujący merge.
- `make test-intelligence-report` to telemetria/trend i nie blokuje merge.
- `make check-new-code-coverage-diagnostics` to opcjonalna diagnostyka manualna (pomocniczy output, bez roli gate).

Domyślna bramka pokrycia:

- diff base: `origin/main`
- minimalne pokrycie zmienionych linii: `80%`

Przydatne opcje:

```bash
NEW_CODE_CHANGED_LINES_MIN=80 make check-new-code-coverage
NEW_CODE_DIFF_BASE=origin/main make check-new-code-coverage
NEW_CODE_AUTO_INCLUDE_CHANGED=1 make check-new-code-coverage
```

Opcjonalny lekki raport intelligence (wpływ czasu testów + kandydaci flaky):

```bash
make test-intelligence-report
```

Raport dopisuje punkt trendu do `test-results/sonar/test-intelligence-history.jsonl`.
Skalibrowane domyślne progi (zadanie 179):
- `TEST_INTEL_SLOW_THRESHOLD=1.8` (próg kandydata do demotion z ci-lite)
- `TEST_INTEL_FAST_THRESHOLD=0.1` (próg kandydata do promotion z new-code)
- `TEST_INTEL_MIN_TESTS_PROMOTION=3` (ogranicza szum dla bardzo małych plików)

Przykład ręcznego override:

```bash
TEST_INTEL_SLOW_THRESHOLD=2.0 TEST_INTEL_FAST_THRESHOLD=0.08 make test-intelligence-report
```

Zachowanie runu new-code coverage:

- bazowe grupy testów: `config/pytest-groups/ci-lite.txt` + `config/pytest-groups/sonar-new-code.txt`
- automatyczne dołączanie testów zmienionych/powiązanych jest domyślnie aktywne (`NEW_CODE_AUTO_INCLUDE_CHANGED=1`)
- wzorzec auto-include dla zmienionych testów: `tests/**/test_*.py`
- resolver listy: `scripts/resolve_sonar_new_code_tests.py` (selekcja katalogowa + metadane: `selection_reason`, `domain`, `legacy_targeted`)
- źródło sync grup: `scripts/sync_pytest_groups_from_catalog.py` (`test_catalog.json` -> `ci-lite/new-code/fast/long/heavy`)
- gdy lokalnie nie ma `ripgrep` (`rg`), resolver używa fallbacku Python (bez blokowania runu)
- w CI backend-lite doinstalowuje `ripgrep` dla szybszego wyboru i czytelnych logów

Kontrakt deterministyczności (dlaczego to nie flakuje):

- `NEW_CODE_TIME_BUDGET_SEC=0` w CI: brak cięcia listy testów przez czas.
- `config/coverage-file-floor.txt`: testy-kotwice dla floor są zawsze dołączane.
- `ripgrep` (`rg`) w CI: stabilny i szybki resolver + czytelne logi.
- `scripts/check_test_catalog.py` dodatkowo waliduje grupy release (`fast/long/heavy`) względem uprawnień lane w katalogu.
- Lokalny guard (`make test-catalog-check`, uruchamiany w `make pr-fast`) blokuje nowe/zmienione testy zostawione wyłącznie w `release` lane.
- Ten guard jest celowo lokalny (na GitHub CI jest wyłączony), żeby łapać błąd wcześniej i nie generować szumu na pipeline po push.

Jak sprawdzić pokrycie lokalnie przed push:

```bash
make check-new-code-coverage
```

Na wyjściu sprawdzaj:

- werdykt changed-lines (`changed-lines coverage`)
- werdykt floor per plik (`OK: coverage floors passed for ... files`)
- artefakty: `test-results/sonar/python-coverage.xml`, `test-results/sonar/python-junit.xml`

Szybki triage (gdy gate failuje):

- fail changed-lines coverage: dołącz brakujące testy lub włącz `NEW_CODE_AUTO_INCLUDE_CHANGED=1`.
- fail coverage floors: brakuje testów-kotwic dla modułu z `config/coverage-file-floor.txt`.
- lokalnie brak `rg`: log pokaże fallback; przy rozjeździe z CI doinstaluj `ripgrep`.

Snapshot jakości (referencja, 2026-02-28):

- Sonar new-code coverage: `90.22%` (wymagane: `>=80%`)
- Sonar overall coverage: `86.9%`
- Quality Gate: `Passed`

### Poziom 4: Walidacja pod wydanie (gdy potrzebna)

Cel: wyższa pewność dla większych zmian lub przed release.

Backend:

```bash
make pytest
```

`make pytest` uruchamia grupy backendu w kolejności: `heavy` -> `long` -> `fast`.

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
- `web-next/coverage/lcov.info` (artefakt opcjonalny/lokalny; tymczasowo nieużywany w bramce coverage Sonara)

Scenariusze performance/latency:

- `docs/PL/TESTING_CHAT_LATENCY.md`
- `npm --prefix web-next run test:perf`
- `pytest tests/perf/test_chat_pipeline.py -m performance`
- `./scripts/run-locust.sh`

## CI i Sonar (referencja)

Wymagane bramki na PR:

- Forbidden Paths Guard (job CI `forbidden-paths`)
- Architecture drift guard (job CI `architecture-drift-guard`)
- Backend lite (pytest): kontrakty lane + guard katalogu/grup + smoke readonly preprod + gate changed-lines coverage
- Frontend lite (lint): lint + unit CI-lite
- OpenAPI Contract (export + TS codegen)
- Quick validator (syntax + CI-lite deps)
- SonarCloud Scan (bugi, podatności, utrzymywalność, duplikacje)
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
- heurystyczny audyt ślepego kodu (Python): `make audit-dead-code`
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
- polityka triage anomalii: `docs/PL/QUALITY_FALSE_GREEN_TRIAGE.md`

### 5) Rozjazd optional dependencies w CI-lite

Typowe wpadki:

- test importuje opcjonalną paczkę, której nie ma w środowisku CI-lite
- brak paczki kończy się `ERROR`/`FAILED` zamiast jawnego `skipped`
- nowy test trafia do runu bez zdefiniowanej polityki zależności

Wskaźniki:

- testy z opcjonalną biblioteką używają `pytest.importorskip(...)`, jeśli dependency nie jest obowiązkowe dla CI-lite
- lekkie zależności systemowe pomocne dla szybkich bramek (np. `ripgrep`) są instalowane w jobie CI-lite
- backend-lite pokazuje jawne `skipped` (a nie import error) dla testów optional-dependency

## Procedura triage dla dead-code (audyt heurystyczny)

Stosuj, gdy `make audit-dead-code` albo `make audit-dead-code-full` raportuje znaleziska.

Kontrakt środowiska dla narzędzi:
- uruchamiaj wyłącznie z repozytoryjnego virtualenv: `source .venv/bin/activate`
- ścieżka vulture jest manualna (bez gate CI): `make audit-dead-code-vulture-install`
- nie instaluj globalnych pakietów Pythona poza `.venv`

1. Potwierdź, czy symbol faktycznie jest nieużywany:
- wyszukaj odwołania w repo (`rg "<nazwa_symbolu>"`)
- sprawdź ścieżki dynamiczne (dekoratory, lookup po stringu, mapy pluginów/rejestry)
2. Jeśli symbol jest faktycznie martwy, usuń go w tym samym PR.
3. Jeśli musi pozostać, dodaj możliwie wąski wyjątek do `config/dead_code_allowlist.txt`:
- preferuj regułę dokładną `path/to/file.py:symbol`
- wildcard `dir/*:symbol` stosuj tylko, gdy to uzasadniona grupa równoważnych przypadków
4. Każdy wpis allowlisty musi mieć krótkie uzasadnienie w opisie PR (owner + warunek usunięcia wyjątku).
5. Ten audyt nie jest samodzielnym blockerem release; jest sygnałem do review. Blokujemy tylko potwierdzone defekty lub naruszenia polityk.
6. Dla wyjątków specyficznych dla vulture używaj `config/dead_code_vulture_allowlist.txt` (`path.py:symbol`, `dir/*:symbol` albo `path.py:line`).
7. `make audit-dead-code-full` jest narzędziem manualnym operatora; nie jest domyślną bramką CI.

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
