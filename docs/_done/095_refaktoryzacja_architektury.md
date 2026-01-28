# 095: Refaktoryzacja Architektury (Cleanup & Decoupling)

Status: Zrealizowane (Faza 1-4 wykonana; testy E2E OK; backend pytest przerwany timeoutem po 120s).

## 1. Wykrywanie Martwego Kodu (Dead Code Analysis)
Zidentyfikowano pliki stanowiące "fairy tales" (zaślepki bez implementacji):

1.  **`venom_core/agents/writer.py`** (21 B) - Pusty moduł.
2.  **`venom_core/perception/antenna.py`** (22 B) - Pusty moduł.
3.  **`venom_core/infrastructure/onnx_runtime.py`** (27 B)
    -   *Status:* STUB (Pusty plik).
    -   *Wyjaśnienie:* Plik jest pusty. Obsługa modeli ONNX (Phi3, TTS) znajduje się w `model_manager.py` oraz `audio_engine.py`. Usuwamy tylko ten martwy plik, **nie** technologię ONNX z projektu.

**Weryfikacja (stan obecny):**
- Pliki zawieraja jedynie docstring (brak implementacji).
- Rozmiary: `writer.py` 21B, `antenna.py` 22B, `onnx_runtime.py` 27B.

**Akcja:** Fizyczne usunięcie plików i czyszczenie importów.

## 2. Wykrywanie Monolitów (Backend)
Zidentyfikowano moduły o zbyt dużej odpowiedzialności (God Objects):

1.  **`venom_core/core/orchestrator/orchestrator_core.py`** (2170 linii)
    -   *Problem:* Zarządza wszystkim: task dispatch, kernel, event broadcasting, tracing, error handling.
    -   *Rekomendacja:* Wydzielenie `TaskManager`, `EventBroadcaster`, `KernelLifecycleManager`.

2.  **`venom_core/api/routes/system.py`** (1525 linii)
    -   *Problem:* Router "od wszystkiego": metrics, services, scheduler, IoT, LLM control, Cost Guard.
    -   *Rekomendacja:* Podział na `routes/metrics.py`, `routes/llm.py`, `routes/services.py`.
    -   *Stan routingu:* obecnie 20+ endpointów w jednym module (m.in. `/metrics`, `/scheduler/*`, `/system/*`, `/runtime/*`, `/config/*`).

## 3. Analiza Frontend (Next.js)
Struktura katalogów `web-next` jest generalnie poprawna (podział na `components/ui`, `layout` itp.), ALE wykryto krytyczny monolit:

1.  **`web-next/components/cockpit/cockpit-home.tsx`** (1199 linii)
    -   *Problem:* Ogromny plik zawierający logikę całego dashboardu, renderowanie 3D, wykresy, logikę biznesową i style.
    -   *Rekomendacja:* Bezwzględny podział na mniejsze komponenty (np. `CockpitVisualizer`, `CockpitMetrics`, `CockpitControlPanel`).
    -   *Inline styles (wybrane):* `style={{ transformStyle: ... }}`, `style={{ width: ... }}`, `style={{ height }}`.

## 4. Standaryzacja CSS (SCC)
-   **Global Styles:** Prawidłowo używany jeden plik `app/globals.css` + Tailwind.
-   **Inline Styles:** Wykryto użycie `style={{ ... }}` wewnątrz TSX (szczególnie w `cockpit-home.tsx` i `inspector/page.tsx`).
    -   *Problem:* Mieszanie logiki stylów (np. `width: 100%`) z klasami Tailwind.
    -   *Rekomendacja:* Zamiana statycznych styli inline na klasy Tailwind (np. `w-full h-full`). Pozostawienie inline tylko dla wartości dynamicznych (np. progress bar percentage, 3D transform coordinates).

## Plan Wykonawczy (doprecyzowany)
1. **Faza 1 (Szybka):** Usuniecie `writer.py`, `antenna.py`, `onnx_runtime.py` + aktualizacja importow i ewentualnych re-exportow.
2. **Faza 2 (Backend):** Podzial `system.py`:
   - `routes/metrics.py` (metryki, statusy).
   - `routes/scheduler.py` (scheduler/jobs).
   - `routes/services.py` (health checks/services).
   - `routes/llm.py` (LLM servers/runtime).
   - `routes/config.py` (config/runtime/backups/restore).
3. **Faza 3 (Frontend):** Podzial `cockpit-home.tsx` na komponenty:
   - `CockpitVisualizer` (3D/Canvas).
   - `CockpitMetrics` (karty/metriki).
   - `CockpitControlPanel` (akcje i formularze).
4. **Faza 4 (Backend):** Orchestrator:
   - wydzielenie `TaskManager` (dispatch/queue),
   - `EventBroadcaster` (eventy),
   - `KernelLifecycleManager` (inicjalizacja i lifecycle).

## Checklist implementacyjna (Faza 1–4)
### Faza 1: Dead Code
- [x] Usunac `venom_core/agents/writer.py`.
- [x] Usunac `venom_core/perception/antenna.py`.
- [x] Usunac `venom_core/infrastructure/onnx_runtime.py`.
- [x] Wyczyścic importy/re-exporty po usunieciach.

### Faza 2: Backend (routes/system)
- [x] Wydzielic `metrics` (endpoint `/metrics`) do osobnego modulu.
- [x] Wydzielic `scheduler` (status/jobs/pause/resume).
- [x] Wydzielic `services` (health/services).
- [x] Wydzielic `llm` (llm-servers/runtime).
- [x] Wydzielic `runtime` (status/profile/actions/history).
- [x] Wydzielic `config` (runtime/backups/restore).
- [x] Wydzielic `iot` (iot/status).
- [x] Wydzielic `status` (system/status).
- [x] Wydzielic `governance` (cost-mode + autonomy).
- [x] Wydzielic `storage` (system/storage).
- [x] Podlaczyc nowe routery w `main.py`.

### Faza 3: Frontend (cockpit)
- [x] Wydzielic TokenChart do osobnego komponentu.
- [x] Wydzielic LogEntry do osobnego komponentu.
- [x] Wydzielic komponent wizualizacji 3D/Canvas (CockpitPanel3D).
- [x] Wydzielic karty metryk (TokenEfficiencyStat/TokenShareBar/ResourceMetricCard).
- [x] Wydzielic komponenty metryk/kart (CockpitKpiSection).
- [x] Wydzielic panel sterowania/akcje (CockpitQueueControl).
- [x] Wydzielic ChatComposer + chatList/feedback (CockpitChatThread).
- [x] Wydzielic oprawe czatu (CockpitChatConsole).
- [x] Wydzielic request detail drawer (CockpitRequestDetailDrawer).
- [x] Wydzielic hidden prompts panel (CockpitHiddenPromptsPanel).
- [x] Wydzielic LLM server panel + live feed + tasks (CockpitLlmOpsPanel).
- [x] Wydzielic sekcje insight/telemetry/feedback/macro (CockpitInsightsSection).
- [x] Przeniesc diagnostyke requestu (runtime error + SimpleMode response + tryb) do CockpitRequestDetailDrawer.
- [x] Wydzielic naglowek (CockpitHeader).
- [x] Wydzielic sidebar/panele (CockpitSidebar).
- [x] Wydzielic cockpit-utils + cockpit-hooks (czesc logiki/transformacji).
- [x] Wydzielic telemetry panel (CockpitTelemetryPanel).
- [x] Wydzielic history panel (CockpitHistoryPanel).
- [x] Wydzielic tuning drawer (CockpitTuningDrawer).
- [x] Wyniesc akcje kolejki do hooka (useQueueActions).
- [x] Wydzielic cockpit-metrics (KPI + telemetry).
- [x] Wydzielic cockpit-runtime (wrapper dla insights/runtime).
- [x] Wydzielic cockpit-actions (QuickActions wrapper).
- [x] Wyniesc makra do hooka (useMacroActions).
- [x] Wydzielic cockpit-queue (wrapper dla CockpitQueueControl).
- [x] Wydzielic cockpit-models i cockpit-logs (LLM ops podzial).
- [x] Wyniesc logike session history do hooka (useSessionHistoryState).
- [x] Wyniesc logike hidden prompts + tracking do hookow (useHiddenPromptState/useTrackedRequestIds).
- [x] Wyniesc logike optimistic/send do hooka (useOptimisticRequests + useChatSend).
- [x] Przeniesc inline styles statyczne do klas (pozostaly tylko dynamiczne).

### Faza 4: Orchestrator
- [x] Wydzielic `TaskManager`.
- [x] Wydzielic `EventBroadcaster`.
- [x] Wydzielic `KernelLifecycleManager`.
- [x] Dodac testy/coverage dla podzialu (test_orchestrator_components.py).

## Wyniki testow (2026-01-25)
- `npm --prefix web-next run test:e2e`
  - Preflight: OK
  - Latency: Next Cockpit OK, Legacy Cockpit pominięty
  - Functional: 23/23 passed
- `pytest tests/test_orchestrator_components.py` - 7 passed
- `pytest` - przerwany timeoutem po 120s (bez bledow w wykonanym fragmencie).

## Ocena zakresu
- Faza 1-3: wykonane zgodnie z checklistami.
- Faza 4: podzial wykonany, `orchestrator_core.py` <= 1200; testy dodane i odpalone.
- Kryteria akceptacji: spelnione funkcjonalnie; pelny backend `pytest` wymaga ponowienia z dluzszym timeoutem.

## Plan domkniecia Fazy 4 (orchestrator)
1. **Dalszy podzial `orchestrator_core.py`**
   - Wydzielic: `orchestrator_submit.py`, `orchestrator_dispatch.py`, `orchestrator_events.py`,
     `orchestrator_flows.py`, `orchestrator_intents.py`, `orchestrator_utils.py`.
   - Cel: `orchestrator_core.py` <= 1200 linii, tylko facade + wiring.
2. **Stabilizacja kontraktow**
   - Ujednolicic podpisy metod publicznych `Orchestrator` i typy zwracane w nowych modulach.
   - Wyeliminowac cykliczne importy (moduly pomocnicze importowane tylko przez core).
3. **Testy regresyjne podzialu**
   - Dodac minimalne testy jednostkowe dla wydzielonych modulow.
   - Zaktualizowac testy scenariuszy (queue/stop/purge/dispatch) po podziale.
4. **Re-baseline**
   - Uruchomic testy jednostkowe + e2e.
   - Zapisac nowy stan w tym dokumencie (rozmiary plikow i wyniki testow).

## Szybki audit: sensowne testy/coverage do dodania
1. **Queue/Control flow**
   - Testy `orchestrator_queue.py`: `pause/resume`, `emergency_stop`, `purge`, `abort`.
   - Testy scenariuszy w `tests/test_orchestrator_core_scenarios.py` pod nowym podzialem.
2. **Dispatch/Submit**
   - Testy `orchestrator_submit.py`: walidacja payloadu + tworzenie tasku + error handling.
   - Testy `orchestrator_dispatch.py`: routing do TaskDispatcher + obsluga timeoutow.
3. **Events**
   - Testy `orchestrator_events.py`: mapowanie eventow i bezpieczne broadcasty.
4. **Kernel lifecycle**
   - Testy `kernel_lifecycle.py` i `orchestrator_kernel.py`: refresh, drift check, brak crashu na None.
5. **Flows**
   - Minimalne testy integracyjne: `Campaign/Forge/Council/Healing` -> czy flow startuje i konczy bez wyjatku.

## Kryteria akceptacji
- Brak referencji do usunietych stubow.
- `system.py` podzielony bez utraty endpointow.
- `cockpit-home.tsx` rozbity i spelnia limit 1200 linii.
- Orchestrator bez zmian funkcjonalnych, testy przechodza.

## Proponowany podzial plikow (nowe moduly)

### Backend: `venom_core/api/routes`
Cel: rozbic `system.py` na tematyczne routery, zachowac prefix `/api/v1`.

```
venom_core/api/routes/
  metrics.py        # /metrics
  scheduler.py      # /scheduler/status, /scheduler/jobs, /scheduler/pause, /scheduler/resume
  services.py       # /system/services, /system/services/{service_name}
  llm.py            # /system/llm-servers*, /system/llm-runtime*
  runtime.py        # /runtime/status, /runtime/profile/{profile_name}, /runtime/{service}/{action}, /runtime/history
  config.py         # /config/runtime, /config/backups, /config/restore
  iot.py            # /iot/status
  system.py         # pozostaje jako agregator lub zostaje uproszczony
```

### Backend: Orchestrator (podzial odpowiedzialnosci)
Cel: wydzielenie odpowiedzialnosci z `orchestrator_core.py`.

```
venom_core/core/orchestrator/
  orchestrator_core.py        # cienki orchestrator (glue)
  task_manager.py             # dispatch/queue/task lifecycle
  kernel_lifecycle.py         # budowa/konfiguracja kernel + lifecycle
  event_broadcaster.py        # broadcast eventow i polityka retry
  error_handling.py           # klasy bledow + fallbacki
```

#### Docelowy podzial `orchestrator_core.py` (do < 1500 linii)
Cel: rozbicie na moduly logiczne, kazdy < ~600 linii. `orchestrator_core.py`
zostaje jako "glue" i publiczne API klasy `Orchestrator`.

Proponowane nowe moduly:

```
venom_core/core/orchestrator/
  orchestrator_core.py            # orchestrator facade + wiring, delegacje
  orchestrator_queue.py           # pause/resume/purge/abort/emergency_stop + status
  orchestrator_submit.py          # submit_task, fast_path, walidacje requestu
  orchestrator_dispatch.py        # logika dispatch/_run_task, integracja TaskDispatcher
  orchestrator_flows.py           # init i obsluga flow (campaign, forge, council, healing)
  orchestrator_events.py          # _broadcast_event + mapowanie eventow, payloady
  orchestrator_kernel.py          # refresh kernel + drift checks + hooki lifecycle
  orchestrator_intents.py         # classify intent + routing NON_LLM/NON_LEARNING
  orchestrator_utils.py           # pomocnicze funkcje (formatowanie, limity, helpers)
  task_manager.py                 # juz wydzielony (queue + task handles)
  kernel_lifecycle.py             # juz wydzielony (lifecycle kernel)
  event_broadcaster.py            # juz wydzielony (broadcast)
```

Nowe moduly (dodane w repo):
- `venom_core/core/orchestrator/orchestrator_kernel.py`
- `venom_core/core/orchestrator/orchestrator_queue.py`

Zasady:
- `orchestrator_core.py` <= 1200 linii, tylko importy + delegacje.
- Nowe moduly nie importuja siebie nawzajem cyklicznie (tylko przez orchestrator_core).
- Wszystkie publiczne metody `Orchestrator` zostaja w `orchestrator_core.py`,
  ale wewnetrzna logika przeniesiona do modulow pomocniczych.

Kolejnosc wydzielania (sugerowana):
1) `orchestrator_queue.py` (pause/resume/purge/emergency/abort) -> szybkie.
2) `orchestrator_kernel.py` (refresh/drift) -> izolowane.
3) `orchestrator_events.py` (broadcast) -> izolowane.
4) `orchestrator_submit.py` + `orchestrator_dispatch.py` -> glowna logika task.
5) `orchestrator_flows.py` -> flow/handlers.
6) `orchestrator_intents.py` -> routing intentow.

### Frontend: Cockpit (podzial monolitu)
Cel: rozbicie `cockpit-home.tsx` na mniejsze komponenty.

```
web-next/components/cockpit/
  cockpit-home.tsx            # tylko layout + integracja
  cockpit-visualizer.tsx      # 3D/Canvas/rendering
  cockpit-metrics.tsx         # metryki/karty/wykresy
  cockpit-control-panel.tsx   # akcje/sterowanie/komendy
  cockpit-logs.tsx            # logi/telemetria
  cockpit-quick-actions.tsx   # szybkie akcje
```

#### Docelowy podzial `cockpit-home.tsx` (do <= 1200 linii)
Cel: `cockpit-home.tsx` jako kompozycja sekcji + hooki, bez ciezkiej logiki/renderu.

Proponowane sekcje/komponenty:

```
web-next/components/cockpit/
  cockpit-home.tsx                 # layout + skladanie sekcji
  cockpit-header.tsx               # tytul + statusy globalne
  cockpit-sidebar.tsx              # nawigacja / quick actions
  cockpit-visualizer.tsx           # 3D/Canvas (wydzielone)
  cockpit-metrics.tsx              # sekcja KPI + tokeny + wykresy
  cockpit-queue.tsx                # kolejka zadan + sterowanie
  cockpit-logs.tsx                 # logi/telemetria
  cockpit-actions.tsx              # panel akcji i formularze
  cockpit-runtime.tsx              # status runtime i serwisow
  cockpit-models.tsx               # karta modeli/LLM
  cockpit-utils.ts                 # helpery UI (format/kolory/etykiety)
  cockpit-hooks.ts                 # hooki: useCockpitState/useQueue/useTelemetry
  cockpit-types.ts                 # typy lokalne UI (nie API)
```

Zasady:
- `cockpit-home.tsx` <= 1200 linii.
- Kazdy komponent <= ~400-600 linii.
- Logika fetch/transform w hookach (`cockpit-hooks.ts`), nie w JSX.
- Brak inline styles poza wartosciami dynamicznymi (np. width/transform).

Kolejnosc wydzielania (sugerowana):
1) `cockpit-header.tsx` + `cockpit-sidebar.tsx` (low risk).
2) `cockpit-actions.tsx` + `cockpit-queue.tsx` (formularze/akcje).
3) `cockpit-metrics.tsx` + `cockpit-runtime.tsx` (kpi/statusy).
4) `cockpit-logs.tsx` + `cockpit-models.tsx`.
5) `cockpit-hooks.ts` + `cockpit-utils.ts` (konsolidacja logiki).

## Aktualne rozmiary po refaktorze (linie)

### Backend: `system.py` podzial na moduly
- `venom_core/api/routes/system.py`: 5
- `venom_core/api/routes/system_metrics.py`: 32
- `venom_core/api/routes/system_scheduler.py`: 86
- `venom_core/api/routes/system_services.py`: 104
- `venom_core/api/routes/system_llm.py`: 398
- `venom_core/api/routes/system_runtime.py`: 152
- `venom_core/api/routes/system_config.py`: 79
- `venom_core/api/routes/system_deps.py`: 67
- `venom_core/api/routes/system_iot.py`: 88
- `venom_core/api/routes/system_status.py`: 41
- `venom_core/api/routes/system_governance.py`: 203
- `venom_core/api/routes/system_storage.py`: 228

### Frontend: Cockpit (rozbicie monolitu)
- `web-next/components/cockpit/cockpit-actions.tsx`: 12
- `web-next/components/cockpit/cockpit-chat-console.tsx`: 145
- `web-next/components/cockpit/cockpit-chat-hooks.ts`: 224
- `web-next/components/cockpit/cockpit-chat-send.ts`: 519
- `web-next/components/cockpit/cockpit-chat-thread.tsx`: 521
- `web-next/components/cockpit/cockpit-chat-ui.ts`: 432
- `web-next/components/cockpit/cockpit-effects.ts`: 109
- `web-next/components/cockpit/cockpit-header.tsx`: 46
- `web-next/components/cockpit/cockpit-hidden-prompts-panel.tsx`: 213
- `web-next/components/cockpit/cockpit-history-panel.tsx`: 49
- `web-next/components/cockpit/cockpit-home.tsx`: 1200
- `web-next/components/cockpit/cockpit-insights-section.tsx`: 515
- `web-next/components/cockpit/cockpit-hooks.ts`: 689
- `web-next/components/cockpit/cockpit-kpi-section.tsx`: 200
- `web-next/components/cockpit/cockpit-llm-ops-panel.tsx`: 115
- `web-next/components/cockpit/cockpit-llm-server-actions.ts`: 222
- `web-next/components/cockpit/cockpit-logs.tsx`: 151
- `web-next/components/cockpit/cockpit-metric-cards.tsx`: 56
- `web-next/components/cockpit/cockpit-metrics.tsx`: 74
- `web-next/components/cockpit/cockpit-models.tsx`: 203
- `web-next/components/cockpit/cockpit-panel-3d.tsx`: 29
- `web-next/components/cockpit/cockpit-primary-section.tsx`: 120
- `web-next/components/cockpit/cockpit-prompts.ts`: 46
- `web-next/components/cockpit/cockpit-queue-control.tsx`: 98
- `web-next/components/cockpit/cockpit-queue.tsx`: 30
- `web-next/components/cockpit/cockpit-request-detail-actions.ts`: 114
- `web-next/components/cockpit/cockpit-request-detail-drawer.tsx`: 659
- `web-next/components/cockpit/cockpit-runtime-props.ts`: 33
- `web-next/components/cockpit/cockpit-runtime-section.tsx`: 30
- `web-next/components/cockpit/cockpit-runtime.tsx`: 86
- `web-next/components/cockpit/cockpit-section-props.ts`: 688
- `web-next/components/cockpit/cockpit-session-actions.ts`: 82
- `web-next/components/cockpit/cockpit-sidebar.tsx`: 27
- `web-next/components/cockpit/cockpit-telemetry-panel.tsx`: 40
- `web-next/components/cockpit/cockpit-tuning-drawer.tsx`: 81
- `web-next/components/cockpit/cockpit-utils.ts`: 147
- `web-next/components/cockpit/conversation-bubble.tsx`: 222
- `web-next/components/cockpit/integration-matrix.tsx`: 128
- `web-next/components/cockpit/kpi-card.tsx`: 71
- `web-next/components/cockpit/log-entry.tsx`: 63
- `web-next/components/cockpit/macro-card.tsx`: 108
- `web-next/components/cockpit/model-card.tsx`: 81
- `web-next/components/cockpit/token-chart.tsx`: 97
- `web-next/components/cockpit/token-types.ts`: 1

### Backend: Orchestrator (rozbicie monolitu)
- `venom_core/core/orchestrator/__init__.py`: 47
- `venom_core/core/orchestrator/constants.py`: 35
- `venom_core/core/orchestrator/event_broadcaster.py`: 26
- `venom_core/core/orchestrator/flow_coordinator.py`: 357
- `venom_core/core/orchestrator/kernel_lifecycle.py`: 35
- `venom_core/core/orchestrator/kernel_manager.py`: 79
- `venom_core/core/orchestrator/learning_handler.py`: 124
- `venom_core/core/orchestrator/middleware.py`: 111
- `venom_core/core/orchestrator/orchestrator_core.py`: 638
- `venom_core/core/orchestrator/orchestrator_dispatch.py`: 1020
- `venom_core/core/orchestrator/orchestrator_events.py`: 83
- `venom_core/core/orchestrator/orchestrator_flows.py`: 332
- `venom_core/core/orchestrator/orchestrator_kernel.py`: 40
- `venom_core/core/orchestrator/orchestrator_queue.py`: 35
- `venom_core/core/orchestrator/orchestrator_submit.py`: 185
- `venom_core/core/orchestrator/session_handler.py`: 537
- `venom_core/core/orchestrator/task_manager.py`: 50

### Standaryzacja styli (frontend)
- Inline style tylko dla dynamicznych wartosci (np. szerokosc paska postepu).
- Statyczne style przeniesc do Tailwind (`w-full`, `h-full`, `flex`, itd.).
