# Wytyczne dla Agentów Kodowania (PL)

Ten plik zawiera **instrukcje dla agentów kodowania** pracujących w tym repozytorium.

Jeśli szukasz listy agentów systemu Venom, użyj:
- [SYSTEM_AGENTS_CATALOG.md](SYSTEM_AGENTS_CATALOG.md)

## Zasady Bazowe

- Wprowadzaj zmiany małe, testowalne i łatwe do review.
- Utrzymuj jakość typowania (`mypy venom_core` powinno przechodzić).
- Utrzymuj bezpieczeństwo (znaleziska Sonar/Snyk naprawiamy, nie ignorujemy).
- Unikaj martwego kodu i placeholderów.
- Ścieżki błędów mają być jawne i, gdzie sensowne, pokryte testami.
- Przed uruchamianiem narzędzi Pythona aktywuj środowisko repo: `source .venv/bin/activate`.

## Domyślna Komenda Testów (zacznij od tego)

Gdy zakres testów nie jest jeszcze doprecyzowany, zacznij od:

```bash
source .venv/bin/activate
pytest -q
```

## Kontrakt Dostarczania Bez Limitów Czasu (obowiązkowy)

To jest domyślny tryb pracy dla GitHub Coding Agent i ma pierwszeństwo przed długą eksploracją.

Obietnice oparte o minuty są zabronione. Agent może być wznawiany/wstrzymywany z zewnątrz, więc limity minutowe nie są wiarygodnym mechanizmem kontroli.

Checkpointy postępu:

1. tylko preflight (`git status`, pliki docelowe, wymagane narzędzia/env),
2. implementacja minimalnego zakresu end-to-end,
3. pierwszy commit od razu po przygotowaniu pierwszego spójnego wycinka zmian (WIP dozwolony, nawet jeśli gate nie są jeszcze zielone),
4. domknięcie zakresu + testy celowane,
5. `make pr-fast`, poprawki blockerów, raport końcowy.

Twarde zasady stop:

1. Brak ponownej eksploracji repo po rozpoczęciu implementacji.
2. Maksymalnie jedno wywołanie subagenta na fazę (explore/implement/verify).
3. Jeśli dwie kolejne iteracje pracy nie wnoszą zmiany w kodzie ani zmiany w testach, przerwij i zgłoś bloker.
4. Jeśli ten sam gate failuje 2 razy bez zmiany kodu/środowiska, przerwij i zgłoś bloker.
5. Nie uruchamiaj ciężkich checków nieobowiązkowych przed zielonym `make pr-fast`.

Dyscyplina commitów:

1. Pierwszy commit ma powstać od razu po pierwszym spójnym wycinku zmian; nie odkładaj wszystkiego na koniec.
2. Preferuj 1-3 małe commity zamiast jednego dużego na końcu.
3. Nie odkładaj wszystkich commitów na koniec długiej pętli debugowania.

## Szybki Bootstrap (instalacja pakietów)

Gdy stan środowiska jest niepewny, użyj tej sekwencji:

```bash
test -f .venv/bin/activate || python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-ci-lite.txt
```

Opcjonalnie dla zakresu ONNX/runtime:

```bash
python -m pip install -r requirements-extras-onnx.txt
```

Nie opieraj pracy na jednorazowym `pip install ...` bez wskazania właściwego pliku `requirements-*.txt`.

Bootstrap frontendu (obowiązkowy przy zakresie frontend):

```bash
npm --prefix web-next ci
```

Nie diagnozuj faili testów frontendu przed wykonaniem `npm ci` w `web-next`.

## Zmienne środowiskowe (pewne ładowanie)

Jeśli testy zależą od `.env.dev`, ładuj zmienne jawnie:

```bash
set -a
source .env.dev
set +a
```

Dla smoke preprod używaj targetu `make`, który ustawia kontrakt środowiskowy:

```bash
make test-preprod-readonly-smoke
```

## Bezpieczne uruchamianie gate (obowiązkowe)

Aby uniknąć fałszywie zielonych raportów:

1. nie łącz `cd` i `make` przez `&` (używaj `&&`),
2. nie oceniaj statusu gate tylko po skróconym logu,
3. przy pipeline (`| tail`) włącz `pipefail` i sprawdź `PIPESTATUS[0]`.

Wzorzec rekomendowany:

```bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
make pr-fast
```

Wzorzec z `tail` (nadal poprawny):

```bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
make pr-fast 2>&1 | tail -n 200
test ${PIPESTATUS[0]} -eq 0
```

Ważne:

1. `... | tail ...` domyślnie zwraca status `tail`, nie komendy źródłowej.
2. Zawsze używaj `set -o pipefail` i sprawdzaj `PIPESTATUS[0]`, gdy log jest pipowany.

## Playbook Uruchamiania Testów (obowiązkowy, dokładna kolejność)

Testy uruchamiaj z roota repo i z aktywnym virtualenv:

```bash
cd "$(git rev-parse --show-toplevel)"
source .venv/bin/activate
```

1. Bootstrap backendu (gdy środowisko jest świeże/zmienione):

```bash
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-ci-lite.txt
```

2. Bootstrap frontendu (obowiązkowo, jeśli zmieniasz `web-next`):

```bash
npm --prefix web-next ci
```

3. Testy celowane przed hard gate:
   - zakres backend:

```bash
pytest -q tests/<path_or_file>.py
```

   - zakres frontend:

```bash
make test-web-unit
```

   - gdy dotykasz zakresu e2e:

```bash
make test-web-e2e
```

4. Diagnostyka metadanych/coverage dla zmienionego kodu/testów Python:

```bash
make test-catalog-check
make test-groups-check
make check-new-code-coverage-diagnostics
```

5. Finalna bramka obowiązkowa (dla każdego zakresu poza markdown-only):

```bash
make pr-fast
```

Domyślne profile komend (wybierz dokładnie jeden, zgodnie z zakresem):

Zakres tylko Python:

```bash
source .venv/bin/activate
make test-ci-lite
make test-catalog-check
make test-groups-check
make check-new-code-coverage-diagnostics
make pr-fast
```

Zakres tylko frontend:

```bash
source .venv/bin/activate
npm --prefix web-next ci
make test-web-unit
make pr-fast
```

Zakres mieszany backend+frontend:

```bash
source .venv/bin/activate
npm --prefix web-next ci
make test-web-unit
make test-ci-lite
make test-catalog-check
make test-groups-check
make check-new-code-coverage-diagnostics
make pr-fast
```

Recovery przy failu metadanych testów:

```bash
make test-catalog-sync
make test-groups-sync
make test-catalog-check
make test-groups-check
make check-new-code-coverage-diagnostics
```

## Polityka Hard Gate (obowiązkowa)

Agent kodowania nie może kończyć zadania przy czerwonych bramkach jakości.

Obowiązkowa sekwencja przed zakończeniem:

1. `make pr-fast`

Uwaga: `make pr-fast` uruchamia wewnętrznie gate pokrycia nowego kodu.
Samodzielne `make check-new-code-coverage` zostaje jako komenda diagnostyczna/manualna.

Jeśli którykolwiek gate failuje:

1. napraw problem,
2. uruchom ponownie gate,
3. powtarzaj aż do zielonego wyniku lub potwierdzonego blokera środowiskowego.

Tryb "partial done" przy failujących gate'ach jest zabroniony.

Ścieżka blokera środowiskowego:

1. ustaw `HARD_GATE_ENV_BLOCKER=1` dla wykonania hooka hard-gate,
2. obowiązkowo opisz bloker i jego wpływ w sekcji ryzyk/ograniczeń PR.

## Dwustopniowy Przepływ Jakości (GitHub Agent + Nadzorca)

Aby sesje GitHub Coding Agent były przewidywalne i domykane deterministycznie, stosujemy 2 etapy:

Etap A: Bramka sesji (GitHub Coding Agent, obowiązkowa przed handoffem)

1. realizacja zakresu bez pętli re-eksploracji,
2. co najmniej jeden commit od razu po pierwszym spójnym wycinku zmian,
3. testy celowane dla zmienionych modułów,
4. uruchomienie:
   - `make test-groups-check`
   - `make check-new-code-coverage-diagnostics`
5. raport handoff z blockerami i dokładnymi komendami, które failują.

Etap B: Bramka merge (agent nadzorca / owner końcowy, obowiązkowa przed merge)

1. pełne `make pr-fast`,
2. naprawa pozostałych faili,
3. merge tylko przy zielonym finalnym gate.

Zasada:

1. Etap A nie zastępuje Etapu B.
2. Etap B pozostaje ostateczną decyzją jakościową repo.

## Szybka ścieżka dla Markdown (wyjątek)

Dla zadań wyłącznie markdownowych można pominąć ciężkie bramki lokalne.

Zakres markdown-only (wszystkie zmienione pliki muszą pasować):
1. każda zmieniona ścieżka kończy się na `.md` (dowolny katalog)

Zasady:
1. Jeśli choć jeden zmieniony plik jest poza zakresem markdown-only, obowiązuje pełna polityka hard-gate.
2. Dla zakresu markdown-only pomijamy:
   - `make pr-fast`
3. W raporcie końcowym obowiązkowo dopisać: "zmiana markdown-only, hard gate pominięte zgodnie z polityką".

## Kontrakt raportu końcowego (obowiązkowy)

Raport końcowy (oraz opis PR) musi zawierać:

1. listę wykonanych komend walidacyjnych,
2. wynik pass/fail dla każdej komendy,
3. changed-lines coverage z outputu `make pr-fast` (lub `N/A` dla zmian markdown-only, gdy gate pominięto zgodnie z polityką),
4. znane ryzyka/skipy z uzasadnieniem.

Baza formatu: `.github/pull_request_template.md`.

## Wymagana Walidacja Przed PR

- Najpierw uruchamiaj szybkie checki (lint + testy celowane).
- Uruchamiaj odpowiednie grupy `pytest` dla zmienianych modułów.
- Potwierdź brak nowych podatności critical/high.

## Bramka Coverage: dlaczego "testy zielone" nadal może failować

`make pr-fast` sprawdza changed-lines coverage względem diffa (`origin/main`), a nie tylko sam status testów.

Gdy coverage gate failuje mimo dopisanych testów:

1. uruchom `make check-new-code-coverage-diagnostics`,
2. sprawdź spójność katalogu i grup:
   - `make test-catalog-check`
   - `make test-groups-check`
3. gdy potrzeba, zsynchronizuj:
   - `make test-catalog-sync`
   - `make test-groups-sync`

Fail `check-file-coverage-floor` jest blokujący. Nie klasyfikuj go jako „stary problem” bez jawnej reprodukcji na czystym `origin/main`.

Triage coverage-floor (wymagany, minimalny):

1. uruchom pełny `make pr-fast` (bez ścieżki decyzyjnej opartej tylko o `grep/head`),
2. potwierdź próg w `config/coverage-file-floor.txt`,
3. odtwórz wynik na czystym `origin/main`,
4. jeśli `origin/main` przechodzi, bieżący diff jest regresją i trzeba go naprawić.

Antywzorce:

1. `git stash && make ... | grep ... | head ...` jako dowód,
2. teza „to stary problem” bez reprodukcji na czystym main.

## Protokół Rejestracji Nowych Testów (obowiązkowy)

Przy dopisywaniu nowych testów dla zmienionego kodu wykonaj w tym samym PR:

1. dodaj plik testu w `tests/`,
2. zarejestruj test w `config/testing/test_catalog.json`,
3. dla pokrycia changed-code ustaw lane:
   - `primary_lane: "new-code"`
   - `allowed_lanes: ["new-code", "ci-lite", "release"]`
4. uruchom `make test-groups-sync`,
5. potwierdź obecność testu w `config/pytest-groups/sonar-new-code.txt`,
6. uruchom `make check-new-code-coverage-diagnostics`.

Znany pitfall (krytyczny):

1. `make pr-fast` uruchamia selekcję nowego kodu z `NEW_CODE_EXCLUDE_SLOW_FASTLANE=1`.
2. Pliki pasujące do slow-patternów z `scripts/resolve_sonar_new_code_tests.py` mogą zostać wycięte z selekcji coverage.
3. Aktualne slow-patterny ścieżek zawierają m.in. `integration` i `benchmark`.
4. Jeśli test ma brać udział w changed-code coverage, unikaj tych tokenów w nazwie/ścieżce testu.

Wymagana konwencja nazewnictwa nowych testów:

1. Używaj neutralnych nazw, np. `tests/test_coding_run_service.py`.
2. Unikaj tokenów slow-pattern w nazwie/ścieżce:
   - `benchmark`
   - `integration`
3. Jeśli test został już dodany z blokującym tokenem, zrób rename w tym samym PR.

Minimalna checklista walidacyjna (kolejność obowiązkowa):

```bash
make test-groups-sync
make test-groups-check
rg "tests/test_<new_name>\\.py" config/pytest-groups/sonar-new-code.txt
make check-new-code-coverage-diagnostics
make pr-fast
```

Zasada interpretacji:

1. Jeśli testu nie ma w `sonar-new-code.txt`, nie przechodź do `make pr-fast`.
2. Najpierw popraw katalog/lane/nazewnictwo, potem uruchom checklistę ponownie.

## Zasada i18n Komunikatów Użytkownika (obowiązkowa)

- Każdy komunikat widoczny dla użytkownika (labelki UI, przyciski, toasty, modale, błędy walidacji, błędy API pokazywane w UI, teksty empty-state) musi być realizowany przez klucze tłumaczeń, bez hardkodowanych stringów.
- Dla nowych lub zmienionych komunikatów trzeba dodać/uzupełnić tłumaczenia we wszystkich wspieranych językach: `pl`, `en`, `de`.
- Zachowuj spójny namespace kluczy i pełną parzystość między plikami locale (bez brakujących kluczy w jednym języku).
- Nie mergujemy zmian powodujących miks języków w UI przez fallback do hardkodu.

## Zasada Świadomości Stosu CI

- Przed dodaniem/aktualizacją testów dla CI-lite sprawdź, jakie zależności i narzędzia są dostępne w stosie CI-lite.
- Używaj `requirements-ci-lite.txt`, `config/pytest-groups/ci-lite.txt` oraz `scripts/audit_lite_deps.py` jako źródła prawdy.
- Jeśli test wymaga opcjonalnej paczki, której nie ma gwarantowanej w CI-lite, użyj `pytest.importorskip(...)` albo przenieś test poza lekką ścieżkę.

## Stos Narzędzi Jakości i Bezpieczeństwa (Standard Projektu)

- **SonarCloud (bramka PR):** obowiązkowa analiza pull requestów pod kątem bugów, podatności, code smelli, duplikacji i utrzymywalności.
- **Snyk (skan okresowy):** cykliczne skany bezpieczeństwa zależności i kontenerów pod nowe CVE.
- **CI Lite:** szybkie checki na PR (lint + wybrane testy unit).
- **pre-commit:** lokalne hooki wymagane przed push.
- **Lokalne checki statyczne:** `ruff`, `mypy venom_core`.
- **Lokalne testy:** `pytest` (co najmniej celowane zestawy dla zmienionych modułów).

Rekomendowana sekwencja lokalna:

```bash
pre-commit run --all-files
ruff check . --fix
ruff format .
mypy venom_core
pytest -q
```

## Referencja Kanoniczna

- Źródło prawdy dla bramek jakości/bezpieczeństwa: `README_PL.md` sekcja **"Bramy jakości i bezpieczeństwa"**.
- Runbook branch protection i required checks: `.github/BRANCH_PROTECTION.md`.
- Konfiguracja hooków agenta: `.github/hooks/hard-gate.json`.
- Runbook access management: `.github/CODING_AGENT_ACCESS_MANAGEMENT.md`.
- Polityka MCP: `.github/CODING_AGENT_MCP_POLICY.md`.
- Profile custom agents: `.github/agents/`.
- Bootstrap środowiska Copilot coding-agent: `.github/workflows/copilot-setup-steps.yml`.
- Anti-loop template zadania: `.github/coding-agent-task-template.md`.

## Referencje Architektury

- Wizja systemu: `docs/PL/VENOM_MASTER_VISION_V1.md`
- Architektura backendu: `docs/PL/BACKEND_ARCHITECTURE.md`
- Mapa katalogów / drzewo repo: `docs/PL/TREE.md`

## Zasada Dokumentacyjna

- Katalog funkcjonalny agentów runtime Venom jest w `SYSTEM_AGENTS_CATALOG.md`.
- Instrukcje implementacyjne/procesowe dla agentów kodowania są w tym pliku.
