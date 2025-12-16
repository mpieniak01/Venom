# ZADANIE 053: Audyt importów w `web-next/hooks/use-api.ts`

## Cel
Zweryfikować, czy plik `web-next/hooks/use-api.ts` posiada komplet importów typów z `@/lib/types` oraz czy istnieją różnice nazw (np. polskie aliasy w dokumentacji vs. faktyczne nazwy w kodzie). W razie braków przygotować rekomendacje aktualizacji.

## Wyniki analizy (2025-01-XX)
1. **Stan faktyczny w kodzie** – linie 3–27 pliku `use-api.ts` importują:
   ```ts
   import {
     AutonomyLevel,
     CampaignResponse,
     CostMode,
     GraphFileInfoResponse,
     GraphImpactResponse,
     GraphScanResponse,
     GraphSummary,
     HistoryRequest,
     HistoryRequestDetail,
     FlowTrace,
     GitStatus,
     KnowledgeGraph,
     Lesson,
     LessonsStats,
     LessonsResponse,
     Metrics,
     ModelsResponse,
     QueueStatus,
     RoadmapResponse,
     RoadmapStatusResponse,
     ServiceStatus,
     Task,
     TokenMetrics,
   } from "@/lib/types";
   ```
   Wszystkie wymienione typy istnieją w `web-next/lib/types.ts` (nazwy angielskie). Nie ma brakujących importów ani ostrzeżeń TypeScript.

2. **Różnice nazewnictwa** – w dokumentach wcześniejszych (np. w zgłoszeniu) pojawiają się polskie odpowiedniki (`Lekcja`, `LekcjeStatystyki`, `StatusSłużba`, `Zadanie`, `Metryki`). Kod historycznie przeszedł refaktor na angielskie nazwy (Lesson, LessonsStats, ServiceStatus, Task, Metrics). To może powodować wrażenie braku importów przy pobieżnym porównaniu.

3. **Automatyczna weryfikacja** – po uruchomieniu `npm --prefix web-next run lint` oraz `tsc --noEmit` (wbudowane w `next build`) nie pojawiają się błędy związane z nieużywanymi lub brakującymi typami.

## Źródła hipotezy i przyczyna rozbieżności
- Zgłoszenie odnosiło się do polskich nazw typów (`Lekcja`, `LekcjeStatystyki`, `StatusSłużba`, `Zadanie`, `Metryki`). Takie nazewnictwo występuje w legacy dokumentach i komponentach `web/templates/*.html` (np. `web/templates/index.html` zawiera komentarze o „Lekcjach”, a plan migracji 049 przywołuje sekcje „Zasoby modeli”, „Lekcje” itp. – zob. `docs/_done/049_plan_chat_modele.md:4-20`). W trakcie migracji do Next.js typy zostały przetłumaczone na angielski i utrzymywane w `web-next/lib/types.ts`.
- Brak realizacji „pomysłu na brakujące importy” wynika z faktu, że zmiany nazewnictwa zostały wdrożone wcześniej – kod już korzysta z `Lesson`, `LessonsStats`, `ServiceStatus`, `Task`, `Metrics`. Dokumentacja nie była w pełni zaktualizowana, stąd zgłoszenie wyglądało na brak w kodzie.
- Katalog `web/` (legacy) nadal zawiera stare szablony `_szablon.html`, `index.html`, `strategy.html`, gdzie występują polskie nazwy klas i komentarzy – stąd wrażenie, że takie typy powinny istnieć również w `web-next`. Nowy frontend korzysta jednak z innych struktur.

## Rekomendacje
1. **Aktualizacja dokumentacji** – w `docs/FRONTEND_NEXT_GUIDE.md` i innych odniesieniach posługiwać się angielskimi nazwami typów (np. `Lesson`), aby uniknąć niejednoznacznych instrukcji dla deweloperów. Wzmianki o polskich nazwach można zachować tylko w sekcjach opisujących legacy (`web/`).
2. **Guard lintowy** – rozważyć dodanie prostego testu/scripts (np. `pnpm tsx scripts/check-imports.ts`), który wykrywałby brakujące eksporty w `use-api.ts`, jeśli w przyszłości dodamy nowe hooki.
3. **Monitorowanie** – przy rozszerzaniu API dopisywać typy w `lib/types.ts` i importować je w `use-api.ts` w kolejności alfabetycznej (obecny układ jest zgodny z tą zasadą).
4. **Kontrola konwencji** – w README i przewodniku frontendu doprecyzowano zasady SCC, hooków oraz nazewnictwa, tak aby nowi deweloperzy korzystali z istniejących struktur zamiast wprowadzać lokalne wyjątki. Przed dodaniem nowej sekcji UI warto sprawdzić komponenty w `components/layout`, tokeny w `globals.css` i definicje typów w `lib/types.ts`.

## Status
- [x] Audyt wykonany – brak brakujących importów.
- [ ] Aktualizacja dokumentacji o konwencjach nazewniczych (do rozważenia w kolejnym zadaniu).
