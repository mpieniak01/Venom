# 095b: Refaktoryzacja Architektury - Faza 5 (Refaktoryzacja Logiczna)

**Status:** Zakończono / Completed (Zaktualizowano 2026-01-25)
**Powiązane:** [095_refaktoryzacja_architektury.md](./095_refaktoryzacja_architektury.md)

## Kontekst
Faza 1-4 (fizyczne rozdzielenie plików) zakończona sukcesem. Analiza kodu wykazała jednak dług technologiczny w postaci "God Methods" (`orchestrator_dispatch.py`) oraz "God Components" (`cockpit-home.tsx`).
Celem Fazy 5 jest **logiczne rozdzielenie odpowiedzialności** (Logical Decoupling).

## Plan Wykonawczy (Wieloetapowy)

### Faza 5.1: Konsolidacja Metryk (Quick Win)
**Cel:** Wyeliminowanie duplikacji endpointów metryk i posprzątanie nazewnictwa.

1.  **Analiza:**
    -   Sprawdź `venom_core/api/routes/metrics.py` vs `venom_core/api/routes/system_metrics.py`.
    -   Zidentyfikuj unikalne endpointy.
2.  **Implementacja:**
    -   Przenieś logikę z `system_metrics.py` do `metrics.py`.
    -   Ujednolić prefix API (np. `/api/v1/metrics`).
    -   Ujednolić prefix API (np. `/api/v1/metrics`).
    -   Zamiast usuwać `system_metrics.py`, zdecydowano o unifikacji nazewnictwa wokół prefiksu `system_*`. Plik `metrics.py` został przemianowany na `system_metrics.py` (**151 LOC**), a importy zaktualizowane.
3.  **Weryfikacja:**
    -   Uruchomienie backendu (`make api`).
    -   Sprawdzenie endpointu `/health` i `/metrics`.
    -   Uruchomienie testów: `pytest tests/test_api_metrics.py` (jeśli istnieje) lub stworzenie nowego.

### Faza 5.2: Orchestrator Pipeline (Core Logic)
**Cel:** Rozbicie metody `run_task` (800 linii) na czytelny pipeline. Obecnie `orchestrator_dispatch.py` ma **340 LOC**.

1.  **Przygotowanie:**
    -   Utwórz strukturę: `venom_core/core/orchestrator/pipeline/`.
2.  **Dekompozycja `run_task`:**
    -   **Krok 1 (Walidacja):** Wydziel `TaskValidator` do `pipeline/task_validator.py` (**161 LOC**).
        -   Logic: Sprawdzanie limitów, pustego promptu, uprawnień.
    -   **Krok 2 (Kontekst):** Wydziel `ContextBuilder` do `pipeline/context_builder.py` (**316 LOC**).
        -   Logic: `prepare_context`, pobieranie historii, RAG.
    -   **Krok 3 (Strategia):** Wydziel `ExecutionStrategy` do `pipeline/execution_strategy.py` (**166 LOC**).
        -   Logic: fast_path, simple_mode vs complex, tool_calls.
    -   **Krok 4 (Wynik):** Wydziel `ResultProcessor` do `pipeline/result_processor.py` (**269 LOC**).
        -   Logic: zapis do pamięci, broadcast eventów, learning logs.
3.  **Integracja:**
    -   Przepisz `run_task` w `orchestrator_dispatch.py` używając nowych klas.
4.  **Weryfikacja:**
    -   `pytest tests/test_orchestrator_core.py` (regresja).
    -   Manualny test chat session.

### Faza 5.3: Frontend State Separation (React Hooks)
**Cel:** Oczyszczenie `cockpit-home.tsx` z logiki biznesowej.

1.  **Zadanie 1: useCockpitLayout**
    -   Wydziel stany UI (dialogi, labMode, sidebar open/close) do `hooks/use-cockpit-layout.ts` (**41 LOC**).
2.  **Zadanie 2: useCockpitChat**
    -   Wydziel logikę inputu, wysyłania wiadomości i historii do `hooks/use-cockpit-interactive-state.ts` (**135 LOC**).
3.  **Zadanie 3: useCockpitMetrics**
    -   Agregacja hooków `useMetrics`, `useServices` itp. w jeden hook `useCockpitData.ts` (**157 LOC**) wywołujący logikę w `use-cockpit-logic.ts` (**619 LOC**).
4.  **Refactor Main Component:**
    -   Przepisz `cockpit-home.tsx` by korzystał tylko z tych hooków. Plik zmniejszono do **355 LOC** (z "God Component").
5.  **Weryfikacja:**
    -   `npm run test:e2e` (Next.js).
    -   Sprawdzenie, czy UI wciąż działa płynnie (brak zbędnych re-renderów).

### Faza 5.5: Model Management & UI Polish
**Cel:** Stabilizacja przełączania modeli oraz dopracowanie warstwy wizualnej.

1. **Model Deduplication:** Naprawiono duplikację tagów w `ModelManager.py` (wybór tagu `:latest` dla tych samych digestów).
2. **Dynamic Filtering:** Zaimplementowano filtrowanie modeli w kokpicie na podstawie wybranego serwera (Ollama/vLLM).
3. **Activation Logic:** Podpięto przycisk "Aktywuj" do backendu, umożliwiając realne przełączanie serwerów LLM.
4. **Header Premium Look:** Naprawiono regresję wizualną nagłówka i tła aplikacji w `CockpitHome.tsx`.
5. **Weryfikacja:** 23 testy Playwright zakończone sukcesem (Smoke + Functional).

---

## checklist implementacyjna

### 5.1 Metrics
- [x] Merge `metrics.py` (logic) -> `system_metrics.py` (naming convention) <!-- id: 0 -->
- [x] Delete old `metrics.py` / Keep `system_metrics.py` (**151 LOC**) <!-- id: 1 -->
- [x] Update `main.py` imports <!-- id: 2 -->
- [x] Verify `/metrics` endpoint <!-- id: 3 -->

### 5.2 Orchestrator
- [x] Create `venom_core/core/orchestrator/task_pipeline/` <!-- id: 4 -->
- [x] Implement `TaskValidator` (**161 LOC**) <!-- id: 5 -->
- [x] Implement `ContextBuilder` (**316 LOC**) <!-- id: 6 -->
- [x] Implement `ExecutionStrategy` (**166 LOC**) <!-- id: 7 -->
- [x] Implement `ResultProcessor` (**269 LOC**) <!-- id: 8 -->
- [x] Refactor `orchestrator_dispatch.py` (Reduced to **340 LOC**) <!-- id: 9 -->
- [x] Run backend tests <!-- id: 10 -->

### 5.3 Frontend
- [x] Create `use-cockpit-layout.ts` (**41 LOC**) <!-- id: 11 -->
- [x] Create `use-cockpit-interactive-state.ts` (**135 LOC**) (replaces use-cockpit-chat.ts) <!-- id: 12 -->
- [x] Create `use-cockpit-data.ts` (**157 LOC**) <!-- id: 13 -->
- [x] Create `use-cockpit-logic.ts` (**619 LOC**) <!-- id: 13b -->
- [x] Refactor `cockpit-home.tsx` (Logic moved to `hooks/use-cockpit-logic.ts`, View: **355 LOC**) <!-- id: 14 -->
- [x] Run frontend E2E tests (Playwright: 23 passed) <!-- id: 15 -->

### 5.5 Model & UI Optimization
- [x] **Model Deduplication:** Fixed Ollama tags in `ModelManager.py`. <!-- id: 20 -->
- [x] **Server Filtering:** Implemented server-based model filtering in `CockpitHome.tsx`. <!-- id: 21 -->
- [x] **Activation Wiring:** Functional LLM server switching in Cockpit UI. <!-- id: 22 -->
- [x] **UI Restoration:** Fixed header layout and background gradient regression. <!-- id: 23 -->
- [x] **Runtime Fix:** Resolved `onChange is not a function` error in selectors. <!-- id: 24 -->

## Kryteria Sukcesu
1. Endpointy działają identycznie jak przed zmianą.
2. `orchestrator_dispatch.py` < 300 linii.
3. `cockpit-home.tsx` zawiera głównie JSX (View) i jest zgodny z "premium look".
4. Wszystkie testy (pytest + playwright) przechodzą bezbłędnie.
5. Transpozycja testów backendowych zakończona sukcesem.

## Hotfixes (Post-Refactor)

### 5.4 Bug Fixes & Stability
- [x] **Double Rendering Fix:** Updated `cockpit-chat-send.ts` to reconcile optimistic IDs with server Task IDs. <!-- id: 16 -->
- [x] **Empty Details Sidebar:** Wired `useCockpitRequestDetailActions` in `use-cockpit-logic.ts`. <!-- id: 17 -->
- [x] **Type Safety:** Resolved MyPy/TypeScript errors across the stack. <!-- id: 18 -->
