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
cd /home/runner/work/Venom/Venom
make pr-fast
```

Wzorzec z `tail` (nadal poprawny):

```bash
set -euo pipefail
cd /home/runner/work/Venom/Venom
make pr-fast 2>&1 | tail -n 200
test ${PIPESTATUS[0]} -eq 0
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

## Szybka ścieżka dla dokumentacji (wyjątek)

Dla zadań wyłącznie dokumentacyjnych można pominąć ciężkie bramki lokalne.

Zakres doc-only (wszystkie zmienione pliki muszą pasować):
1. `docs/**`
2. `docs_dev/**`
3. `README.md`
4. `README_PL.md`
5. inne pliki `*.md` w katalogu głównym repo

Zasady:
1. Jeśli choć jeden zmieniony plik jest poza zakresem doc-only, obowiązuje pełna polityka hard-gate.
2. Dla zakresu doc-only pomijamy:
   - `make pr-fast`
3. W raporcie końcowym obowiązkowo dopisać: "zmiana doc-only, hard gate pominięte zgodnie z polityką".

## Kontrakt raportu końcowego (obowiązkowy)

Raport końcowy (oraz opis PR) musi zawierać:

1. listę wykonanych komend walidacyjnych,
2. wynik pass/fail dla każdej komendy,
3. changed-lines coverage z outputu `make pr-fast`,
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

## Referencje Architektury

- Wizja systemu: `docs/PL/VENOM_MASTER_VISION_V1.md`
- Architektura backendu: `docs/PL/BACKEND_ARCHITECTURE.md`
- Mapa katalogów / drzewo repo: `docs/PL/TREE.md`

## Zasada Dokumentacyjna

- Katalog funkcjonalny agentów runtime Venom jest w `SYSTEM_AGENTS_CATALOG.md`.
- Instrukcje implementacyjne/procesowe dla agentów kodowania są w tym pliku.
