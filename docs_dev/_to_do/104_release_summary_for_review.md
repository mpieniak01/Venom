# Podsumowanie wydania (103+104 łącznie)

Data: 2026-02-01
Gałąź: 103_translations_continuation

## Zakres
Jedno wydanie łączące pierwotny zakres i18n z zadania 103 oraz stabilizacje opisane w 104.

## Kluczowe zmiany
1) i18n + spójność UI
- Rozszerzenie/aktualizacja locale (PL/EN/DE).
- Inicjalizacja locale w Day.js dla poprawnego formatowania dat.
- Ujednolicenie tekstów UI w komponentach Cockpit/Brain/Config.

2) API + stabilizacja testów
- Dependency overrides w testach; cleanup fixtures dla memory/lessons.
- Kompatybilne parsowanie lekcji w grafie pamięci (mock-safe, dict-friendly).
- Naprawione błędy mypy w mapowaniu lekcji w grafie pamięci.

3) Stabilizacja E2E
- Parser SSE akceptuje payload jako obiekt oraz JSON-string.
- Deterministyczny język w E2E (venom-language=pl).
- Oczekiwanie na hydrację w testach Playwright, by uniknąć flaków SSR.

4) Niezawodność suite testów
- Kolejność testów light ustawiona tak, by najdłuższe startowały jako pierwsze.
- Flaky testy core nervous system przeniesione na sync client + polling zakończenia.

## Najważniejsze pliki
- web-next/hooks/use-task-stream.ts
- web-next/lib/i18n/index.tsx
- web-next/tests/*.spec.ts (smoke, chat-mode-routing, chat-context-icons, streaming)
- venom_core/api/routes/memory.py
- tests/test_core_nervous_system.py
- config/pytest-groups/light.txt

## Weryfikacja
- Przeszły wybrane zestawy pytest (memory + api dependencies + core nervous system).
- Zestaw Playwright functional ustabilizowany; smoke i chat mode przechodzą po poprawkach hydracji i języka.

## Uwagi dla recenzentów
- Wydanie celowo łączy 103 + 104, aby ograniczyć churn.
- MCP pozostaje wymagane (proxy już w użyciu); zależności pozostają w requirements.txt.
