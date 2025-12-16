# ZADANIE 054.1 (DONE): Uwagi z review PR #157

## Najważniejsze wnioski
1. **Cockpit (`components/cockpit/cockpit-home.tsx`)** – komponent przekracza 2k linii. Zadanie refaktoryzacji (wydzielenie hooków, formatterów, optimistic UI) przeniesiono do `docs/_to_do/056_refaktoryzacja_paneli_ui.md`.
2. **Inspector (`app/inspector/page.tsx`)** – hook zaznaczenia elementu wymaga kompletnych zależności; ESLint disable został usunięty.
3. **Brain (`components/brain/brain-home.tsx`)** – pomocnicze funkcje/typy mają trafić do modułów wspólnych (również w zadaniu 056).
4. **SSE backend** – przyszły kierunek to event-driven `StateManager → asyncio.Queue`. Zaplanowano w zadaniu 056.
5. **Artefakty testowe** – dodano wzorce `**/test-results/`, `web-next/playwright-report/`, `perf-artifacts/` do `.gitignore`; repo oczyszczone ze starych plików.
7. **Inspector – nadmiarowe odświeżanie** – ekran `/inspector` aktualnie co sekundę przeładowuje wszystkie kafle („Diagnoza przepływu”, „Telemetria requestu”, „Kolejka requestów”). Brak throttlingu powoduje miganie layoutu, mimo że większość danych jest statyczna. Należy wprowadzić:
   - buforowanie wyników `useHistory` / `useTasks` i odświeżanie co kilka sekund,
   - lazy refresh dla „Diagnoza przepływu” (render tylko przy zmianie `selectedId`),
   - płynne animacje liczników zamiast pełnego re-renderu sekcji.
   - [x] 18.12: wprowadzono 5‑sekundowy throttle auto-refreshu zadań + odłączono `handleHistorySelect` od streamów (`web-next/app/inspector/page.tsx`), dzięki czemu panel „Diagnoza przepływu” aktualizuje się tylko przy świadomym wyborze requestu.
   - [x] 18.12: caching `handleHistorySelect` (ignoruje ponowne wywołania dla tego samego requestu, chyba że użytkownik wybierze „Spróbuj ponownie”). Mermaid nie przeładowuje się bez interakcji.
   - [x] 18.12: overlay spinners zastąpione spokojnym przyciskiem bez animacji (lista kolejek pojawia się natychmiast po dopłynięciu danych – zero tekstów „Ładuję…”).
6. **Logowanie SSR (`lib/server-data.ts`)** – `logFetchError` zawsze raportuje błąd (w production używa `console.error` z payloadem), więc utrzymujemy widoczność problemów prefetchu.

## Status działań
- [x] Artefakty testowe ignorowane w git.
- [x] Logger SSR poprawiony.
- [x] Plan refaktoryzacji Cockpit/Brain/SSE przeniesiony do zadania 056.

Dokument służy wyłącznie jako zapis review – kolejne kroki realizujemy w nowych zadaniach backlogu.
