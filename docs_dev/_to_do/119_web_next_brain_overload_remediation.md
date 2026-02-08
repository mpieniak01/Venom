# 119 — Brain-Overload + Readability Remediation (Sonar)

## Cel zadania

Domknięcie zgłoszeń Sonar dla obszaru `web-next`, testów frontendowych oraz `examples/`, dotyczących:
- zbyt wysokiej **Cognitive Complexity**,
- zbyt głębokiego zagnieżdżenia funkcji ("nest functions more than 4 levels deep").
- drobnych zgłoszeń **readability** typu "This pattern can be replaced with ...".

Priorytet: poprawa utrzymywalności bez zmiany zachowania biznesowego UI/UX.

## Zakres wejściowy (lista zgłoszeń)

### A. Cognitive Complexity
- `web-next/app/strategy/page.tsx` — L53 (19 -> <=15)
- `web-next/components/brain/brain-home.tsx` — L288 (56 -> <=15)
- `web-next/components/brain/brain-home.tsx` — L695 (16 -> <=15)
- `web-next/components/cockpit/cockpit-chat-send.ts` — L134 (23 -> <=15)
- `web-next/components/cockpit/cockpit-chat-send.ts` — L217 (38 -> <=15)
- `web-next/components/cockpit/cockpit-chat-thread.tsx` — L371 (39 -> <=15)
- `web-next/components/cockpit/cockpit-kpi-section.tsx` — L67 (21 -> <=15)
- `web-next/components/cockpit/cockpit-llm-server-actions.ts` — L51 (20 -> <=15)
- `web-next/components/cockpit/cockpit-request-detail-drawer.tsx` — L58 (16 -> <=15)
- `web-next/components/cockpit/cockpit-request-detail-drawer.tsx` — L98 (26 -> <=15)
- `web-next/components/cockpit/hooks/use-cockpit-logic.ts` — L571 (79 -> <=15)
- `web-next/components/layout/sidebar.tsx` — L63 (20 -> <=15)
- `web-next/components/layout/status-pills.tsx` — L40 (21 -> <=15)
- `web-next/components/layout/system-status-bar.tsx` — L218 (17 -> <=15)
- `web-next/components/models/models-viewer.tsx` — L247 (65 -> <=15)
- `web-next/lib/date.ts` — L10 (22 -> <=15)
- `web-next/tests/perf/chat-latency.spec.ts` — L56 (22 -> <=15)
- `examples/apprentice_demo.py` — L143 (16 -> <=15)

### B. Nadmierne zagnieżdżenie funkcji
- `web-next/components/brain/brain-home.tsx` — L782
- `web-next/components/cockpit/cockpit-chat-hooks.ts` — L191
- `web-next/components/cockpit/cockpit-chat-send.ts` — L224
- `web-next/components/cockpit/cockpit-chat-send.ts` — L259
- `web-next/components/cockpit/cockpit-chat-send.ts` — L273
- `web-next/components/cockpit/cockpit-chat-send.ts` — L355
- `web-next/components/cockpit/cockpit-chat-send.ts` — L464
- `web-next/components/cockpit/cockpit-chat-send.ts` — L509
- `web-next/components/cockpit/hooks/use-cockpit-logic.ts` — L329
- `web-next/components/config/services-panel.tsx` — L204
- `web-next/tests/chat-context-icons.spec.ts` — L116
- `web-next/tests/chat-context-icons.spec.ts` — L120
- `web-next/tests/chat-mode-routing.spec.ts` — L308
- `web-next/tests/chat-mode-routing.spec.ts` — L427
- `web-next/tests/streaming.spec.ts` — L123

### C. Readability (pattern can be replaced with literal)
- `web-next/app/inspector/page.tsx` — L910 (replaceable with `"`).
- `web-next/app/inspector/page.tsx` — L972 (replaceable with `--`).
- `web-next/components/ui/markdown.tsx` — L94 (replaceable with `&`).
- `web-next/components/ui/markdown.tsx` — L95 (replaceable with `<`).
- `web-next/components/ui/markdown.tsx` — L96 (replaceable with `>`).
- `web-next/components/ui/markdown.tsx` — L97 (replaceable with `"`).
- `web-next/components/ui/markdown.tsx` — zgłoszenie replaceable with `'` (linia wg Sonar).

## Założenia architektoniczne

- Nie zmieniamy kontraktów API backendu.
- Nie zmieniamy semantyki funkcjonalnej UI (tylko refactor strukturalny).
- Preferujemy ekstrakcję małych funkcji pure/helper zamiast dodawania flag/warstw pośrednich.
- W hookach React priorytet: czytelny podział na "state derivation", "actions", "effects".
- W testach e2e preferujemy ekstrakcję helperów scenariuszy i asercji.

## Plan realizacji

### PR-1: Baseline + mapowanie hotspotów
1. Potwierdzenie aktualnych lokalizacji i metryk Sonar dla każdej pozycji.
2. Mapa "issue -> funkcja -> zależności -> ryzyko regresji".
3. Oznaczenie quick-wins (<=15 min) oraz heavy refactorów.

### PR-2: Heavy refactors (najwyższy wpływ)
1. `web-next/components/cockpit/hooks/use-cockpit-logic.ts` (79 -> <=15, nesting).
2. `web-next/components/brain/brain-home.tsx` (56 -> <=15, + nesting).
3. `web-next/components/models/models-viewer.tsx` (65 -> <=15).
4. `web-next/components/cockpit/cockpit-chat-send.ts` (wiele zgłoszeń, complexity + nesting).

### PR-3: Medium refactors (cockpit/layout/strategy)
1. `web-next/app/strategy/page.tsx`.
2. `web-next/components/cockpit/cockpit-chat-thread.tsx`.
3. `web-next/components/cockpit/cockpit-kpi-section.tsx`.
4. `web-next/components/cockpit/cockpit-llm-server-actions.ts`.
5. `web-next/components/cockpit/cockpit-request-detail-drawer.tsx`.
6. `web-next/components/layout/sidebar.tsx`.
7. `web-next/components/layout/status-pills.tsx`.
8. `web-next/components/layout/system-status-bar.tsx`.
9. `web-next/lib/date.ts`.
10. `examples/apprentice_demo.py`.

### PR-4: Test cleanup (frontend e2e)
1. `web-next/tests/chat-context-icons.spec.ts`.
2. `web-next/tests/chat-mode-routing.spec.ts`.
3. `web-next/tests/perf/chat-latency.spec.ts`.
4. `web-next/tests/streaming.spec.ts`.

### PR-5: Readability quick wins (es2021)
1. `web-next/app/inspector/page.tsx` — uproszczenie patternów do literalnych zamienników.
2. `web-next/components/ui/markdown.tsx` — uproszczenie patternów do literalnych zamienników.
3. Weryfikacja, że uproszczenia nie zmieniają semantyki escapingu/formatowania.

## Wzorzec naprawczy (obowiązkowy)

Dla każdego hotspotu:
1. Ekstrakcja warunków i gałęzi do nazwanych helperów (`is*`, `build*`, `map*`).
2. Redukcja głębokości przez early-return i guard clauses.
3. Rozdzielenie odpowiedzialności: logika domenowa vs rendering JSX.
4. Utrzymanie typów TS i kontraktów props/hook.
5. Aktualizacja lub dopisanie testów jednostkowych/integracyjnych dla nowo wydzielonych helperów.

## Kryteria akceptacji

- [ ] Wszystkie wymienione zgłoszenia Sonar przechodzą do stanu `Resolved` (po pełnym reskanie Sonar).
- [ ] Brak nowych `Critical` dla reguł complexity/nesting w dotkniętych plikach (po pełnym reskanie Sonar).
- [x] Zgłoszenia `readability` z sekcji C są zamknięte bez regresji formatowania tekstu.
- [x] `npm --prefix web-next run lint` przechodzi.
- [x] `npm --prefix web-next run build` przechodzi.
- [ ] `make e2e` lub równoważny pakiet testów przechodzi dla zmienionych scenariuszy.
- [ ] Brak regresji funkcjonalnej w kluczowych widokach: Brain, Cockpit, Models, Strategy (do potwierdzenia po e2e/build).
- [ ] Brak regresji funkcjonalnej w demo `examples/apprentice_demo.py` (do potwierdzenia testem/manualem).

## Status realizacji (aktualny)

### Zrealizowane
- `web-next/app/inspector/page.tsx` (readability literals)
- `web-next/components/ui/markdown.tsx` (readability literals)
- `examples/apprentice_demo.py` (obniżenie complexity przez wydzielenie obsługi komend)
- `web-next/app/strategy/page.tsx` (helper extraction)
- `web-next/lib/date.ts` (spłaszczenie logiki relative-time)
- `web-next/components/cockpit/cockpit-kpi-section.tsx` (helper extraction)
- `web-next/components/cockpit/cockpit-request-detail-drawer.tsx` (parser/error helper extraction)
- `web-next/components/layout/sidebar.tsx` (storage/width helper extraction)
- `web-next/components/layout/status-pills.tsx` (tone/status helper extraction)
- `web-next/components/cockpit/cockpit-llm-server-actions.ts` (model/server activation helpers)
- `web-next/components/cockpit/cockpit-chat-thread.tsx` (wydzielenie item renderer i feedback controls)
- `web-next/components/cockpit/cockpit-chat-send.ts` (runtime/payload/reconcile helpers)
- `web-next/components/cockpit/cockpit-chat-send.ts` (kolejne uproszczenie upsert/steps helpers)
- `web-next/components/cockpit/cockpit-chat-send.ts` (wydzielenie standard-task flow do dedykowanego helpera)
- `web-next/components/cockpit/cockpit-chat-hooks.ts` (flatten callback nesting przez helper extraction)
- `web-next/components/cockpit/hooks/use-cockpit-logic.ts` (derived-state helper extraction)
- `web-next/components/cockpit/hooks/use-cockpit-logic.ts` (hydration/feedback effects helper extraction)
- `web-next/components/models/models-viewer.tsx` (cache/storage helper extraction)
- `web-next/components/brain/brain-home.tsx` (style/relation/stats helper extraction, reduced nesting)
- `web-next/components/layout/system-status-bar.tsx` (repo status helper decomposition)
- `web-next/components/config/services-panel.tsx` (WebSocket status-update helper extraction)
- `web-next/tests/chat-context-icons.spec.ts` (SSE mock flattening)
- `web-next/tests/chat-mode-routing.spec.ts` (shared EventSource helper, reduced nesting)
- `web-next/tests/perf/chat-latency.spec.ts` (flow decomposition helpers)
- `web-next/tests/streaming.spec.ts` (SSE mock helper extraction)
- `sonar-project.properties` (CPD exclusions dla locale i18n)

### Do domknięcia przed release
- uruchomienie `make e2e` na środowisku z działającym `http://127.0.0.1:3000` (obecny blocker: preflight fail - cockpit nieosiągalny),
- finalny reskan Sonar i potwierdzenie zamknięcia zgłoszeń z listy wejściowej,
- krótkie manualne sanity-check dla widoków: Cockpit, Models, Strategy, Brain.
