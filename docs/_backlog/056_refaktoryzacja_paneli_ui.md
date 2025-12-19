# ZADANIE 056: Refaktoryzacja paneli UI (Cockpit/Brain)

## Cel
Po stabilizacji funkcjonalności w PR optymalizacyjnym wydzielić duże komponenty frontowe na czytelne moduły, nie przekraczając 700–800 linii na plik.

## Zakres
1. **Cockpit**
   - Hook `useCockpitChat` (optimistic UI, makra, SSE)
   - Hook `useCockpitTelemetry` (event feed, refresh)
   - Po stabilizacji UI: podział na panele (chat/insights/events)
   - Helpery + typy przenieść do `lib/cockpit-formatters.ts`, `components/cockpit/cockpit-types.ts`
2. **Brain**
   - Refaktor odkładamy – wrócić po doprecyzowaniu zakresu panelu (wciąż w tej samej gałęzi, ale jako kolejny krok).
3. **Inspector**
   - Poprawa zależności `useEffect` (`handleHistorySelect` w deps)
4. **StateManager - SSE backend**
   - Projekt event-driven (StateManager → asyncio.Queue).
5. **SSR logging**
   - `web-next/lib/server-data.ts` – strukturalne logowanie błędów także w prod.

## Status
- [ ] Cockpit – hooki + helpery
- [ ] Cockpit – podział na panele (po stabilizacji UX)
- [ ] Brain – refaktor (odłożony)
- [ ] Inspector – deps w `useEffect`
- [ ] Backend – event-driven SSE
- [ ] SSR logging

_Notatka: prace trzymamy na gałęzi `feature/web-next-optimization`, ale wejdą po obecnym PR z optymalizacjami funkcjonalnymi._

## Stan aktualny (audyt 2025-12-18)
- `web-next/components/cockpit/cockpit-home.tsx` liczy ok. 2760 linii i nadal łączy chat, makra, historię i telemetry w jednym komponencie klientowym. Brak wydzielonych hooków (`useCockpitChat`, `useCockpitTelemetry`) powoduje rozrost stanów lokalnych i trudną obsługę SSE.
- `web-next/components/brain/brain-home.tsx` ma ~700 linii z połączoną logiką pobierania (`fetchBrainInitialData`) i renderowaniem kart. Nie wydzielono helperów ani typów do `lib/brain-formatters`.
- W katalogu `web-next/hooks/` wciąż znajdują się jedynie `use-api.ts`, `use-task-stream.ts`, `use-telemetry.ts` – nie ma hooków zdefiniowanych w tym zadaniu. Refaktor pozostaje w 100% do zrealizowania mimo stabilizacji UI.
