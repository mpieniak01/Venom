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

## Polityka Hard Gate (obowiązkowa)

Agent kodowania nie może kończyć zadania przy czerwonych bramkach jakości.

Obowiązkowa sekwencja przed zakończeniem:

1. `make pr-fast`
2. `make check-new-code-coverage`

Jeśli którykolwiek gate failuje:

1. napraw problem,
2. uruchom ponownie obie komendy,
3. powtarzaj aż do zielonego wyniku lub potwierdzonego blokera środowiskowego.

Tryb "partial done" przy failujących gate'ach jest zabroniony.

Ścieżka blokera środowiskowego:

1. ustaw `HARD_GATE_ENV_BLOCKER=1` dla wykonania hooka hard-gate,
2. obowiązkowo opisz bloker i jego wpływ w sekcji ryzyk/ograniczeń PR.

## Kontrakt raportu końcowego (obowiązkowy)

Raport końcowy (oraz opis PR) musi zawierać:

1. listę wykonanych komend walidacyjnych,
2. wynik pass/fail dla każdej komendy,
3. changed-lines coverage z `make check-new-code-coverage`,
4. znane ryzyka/skipy z uzasadnieniem.

Baza formatu: `.github/pull_request_template.md`.

## Wymagana Walidacja Przed PR

- Najpierw uruchamiaj szybkie checki (lint + testy celowane).
- Uruchamiaj odpowiednie grupy `pytest` dla zmienianych modułów.
- Potwierdź brak nowych podatności critical/high.

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
