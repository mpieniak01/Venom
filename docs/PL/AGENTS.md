# Wytyczne dla Agentów Kodowania (PL)

Ten plik zawiera **instrukcje dla agentów kodowania** pracujących w tym repozytorium.

Jeśli szukasz listy agentów systemu Venom, użyj:
- [KATALOG_AGENTOW_SYSTEMU.md](KATALOG_AGENTOW_SYSTEMU.md)

## Zasady Bazowe

- Wprowadzaj zmiany małe, testowalne i łatwe do review.
- Utrzymuj jakość typowania (`mypy venom_core` powinno przechodzić).
- Utrzymuj bezpieczeństwo (znaleziska Sonar/Snyk naprawiamy, nie ignorujemy).
- Unikaj martwego kodu i placeholderów.
- Ścieżki błędów mają być jawne i, gdzie sensowne, pokryte testami.

## Wymagana Walidacja Przed PR

- Najpierw uruchamiaj szybkie checki (lint + testy celowane).
- Uruchamiaj odpowiednie grupy `pytest` dla zmienianych modułów.
- Potwierdź brak nowych podatności critical/high.

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

## Referencje Architektury

- Wizja systemu: `docs/PL/VENOM_MASTER_VISION_V1.md`
- Architektura backendu: `docs/PL/BACKEND_ARCHITECTURE.md`
- Mapa katalogów / drzewo repo: `docs/PL/TREE.md`

## Zasada Dokumentacyjna

- Katalog funkcjonalny agentów runtime Venom jest w `KATALOG_AGENTOW_SYSTEMU.md`.
- Instrukcje implementacyjne/procesowe dla agentów kodowania są w tym pliku.
