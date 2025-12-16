# ZADANIE 054.1: Uwagi z review PR #157

## Wnioski z przeglądu (16.12.2025)
1. **Cockpit (web-next/components/cockpit/cockpit-home.tsx)** – komponent ok. 2000 linii, wymaga podziału na mniejsze moduły + dedykowane hooki (makra, optimistic UI, helpery formatowania).
2. **Inspector (web-next/app/inspector/page.tsx)** – hook automatycznego wyboru requestu powinien mieć pełną tablicę zależności (`handleHistorySelect` zamiast `eslint-disable`).
3. **Brain (web-next/components/brain/brain-home.tsx)** – podobnie jak Cockpit, przenieść funkcje pomocnicze (`formatOperationTimestamp`, `aggregateTags`) i typy do osobnych plików.
4. **SSE backend (venom_core/api/routes/tasks.py)** – obecnie generator oparty na pollingu; w kolejnych iteracjach rozważyć event-driven (asyncio.Queue/Event).
5. **Artefakty testowe (`test-results/`)** – Copilot z PR #157 wskazał, że pliki `.last-run.json` (`test-results/`, `web-next/test-results/`) nie powinny być w repo; dodać katalog do `.gitignore` i usunąć z historii.
6. **SSR logging (`web-next/lib/server-data.ts`)** – `logFetchError` w produkcji nie loguje błędów (wstrzymuje `console.warn`). Warto spiąć z naszym loggerem (np. `server-only logger` albo przesyłanie do backendu), żeby nie tracić informacji o błędach prefetchu w prod.

## Plan uzupełniający
- Zadania refaktoryzacyjne Cockpit/Brain/SSE zostały przeniesione do `docs/_to_do/056_refaktoryzacja_paneli_ui.md`.
- [x] Dodać `test-results/` (+ `web-next/test-results/`) do `.gitignore` i oczyścić repo z tymczasowych artefaktów. _(17.12: wpis w `.gitignore`, `git rm --cached test-results/` oraz `web-next/test-results/`)._
- [x] Zaprojektować sposób logowania błędów SSR w `lib/server-data.ts` (produkcyjne logi, brak `console.warn`). _(17.12: `logFetchError` zawsze loguje; w produkcji używa `console.error` z ustrukturyzowanym payloadem)._
