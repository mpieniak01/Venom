# 123 — SonarQube Maintainability Batch (CC + Duplicated Literals + Typing)

## Źródło

Analiza przygotowana na podstawie wsadu:
- `venom_spore/home/ubuntu/venom/docs_dev/_to_do/123_wsad.md`

## Cel zadania

Domknięcie kolejnej fali zgłoszeń SonarQube (głównie maintainability) bez zmiany logiki biznesowej:
- redukcja **Cognitive Complexity**,
- usunięcie duplikacji literałów (`Define a constant...`),
- domknięcie 2 zgłoszeń `typing mismatch`,
- domknięcie 1 zgłoszenia `nest functions more than 4 levels deep` (frontend testy).

## Snapshot zakresu

- Łącznie: **147** zgłoszeń SonarQube.
- Pliki: **106**.
- Typy zgłoszeń:
  - **114** × `Refactor this function to reduce its Cognitive Complexity...`
  - **30** × `Define a constant instead of duplicating this literal...`
  - **2** × `Change this argument; Function ... expects a different type`
  - **1** × `Refactor this code to not nest functions more than 4 levels deep`

Priorytet realizacyjny: `Critical/High` z wsadu.

## Zakres wejściowy (grupy)

### A. Quick wins: duplicated literals (30)

Najważniejsze pliki do szybkiego zbicia długu:
- `examples/apprentice_integration_example.py`
- `examples/ghost_agent_demo.py`
- `examples/hive_demo.py`
- `examples/memory_demo.py`
- `examples/shadow_demo.py`
- `scripts/genesis.py`
- `venom_core/agents/executive.py`
- `venom_core/agents/guardian.py`
- `venom_core/api/routes/benchmark.py`
- `venom_core/api/routes/models_config.py`
- `venom_core/api/routes/models_install.py`
- `venom_core/api/routes/models_registry.py`
- `venom_core/api/routes/models_registry_ops.py`
- `venom_core/core/ota_manager.py`
- `venom_core/core/token_economist.py`
- `venom_core/execution/skills/docs_skill.py`
- `venom_core/execution/skills/google_calendar_skill.py`
- `venom_core/execution/skills/input_skill.py`
- `venom_core/execution/skills/platform_skill.py`
- `venom_core/execution/skills/web_skill.py`
- `venom_core/infrastructure/docker_habitat.py`
- `venom_core/infrastructure/message_broker.py`
- `venom_core/infrastructure/stack_manager.py`
- `venom_core/memory/vector_store.py`
- `venom_core/perception/recorder.py`
- `venom_spore/skill_executor.py`

### B. Typing mismatch (2)

- `tests/test_benchmark_service_activation.py` (L91)
- `tests/test_helpers.py` (L70)

Decyzja: dopasowanie argumentów do sygnatur (cast/protocol/test-double), bez zmiany semantyki testów.

### C. Cognitive Complexity (114)

#### C1. Skrypty / examples / tests
- `scripts/bench/compare_llm.py` (2 hotspoty)
- `scripts/genesis.py` (1 hotspot)
- `tests/conftest.py`
- `tests/perf/chat_pipeline.py`
- `tests/perf/test_latency_modes_e2e.py`
- `tests/perf/test_llm_latency_e2e.py`
- `tests/perf/test_llm_simple_e2e.py`

#### C2. `venom_core/agents/**`
- `venom_core/agents/__init__.py`
- `venom_core/agents/architect.py`
- `venom_core/agents/base.py`
- `venom_core/agents/chat.py` (3 hotspoty)
- `venom_core/agents/coder.py`
- `venom_core/agents/documenter.py`
- `venom_core/agents/executive.py`
- `venom_core/agents/foreman.py`
- `venom_core/agents/ghost_agent.py` (2 hotspoty)
- `venom_core/agents/operator.py`
- `venom_core/agents/professor.py` (2 hotspoty)
- `venom_core/agents/release_manager.py`
- `venom_core/agents/shadow.py`
- `venom_core/agents/strategist.py`
- `venom_core/agents/system_status.py`
- `venom_core/agents/ux_analyst.py`

#### C3. `venom_core/api/routes/**`
- `venom_core/api/routes/feedback.py` (2)
- `venom_core/api/routes/flow.py`
- `venom_core/api/routes/git.py`
- `venom_core/api/routes/knowledge.py`
- `venom_core/api/routes/learning.py`
- `venom_core/api/routes/llm_simple.py`
- `venom_core/api/routes/memory.py` (2)
- `venom_core/api/routes/models_config.py`
- `venom_core/api/routes/models_install.py`
- `venom_core/api/routes/models_registry.py`
- `venom_core/api/routes/models_utils.py`
- `venom_core/api/routes/system_llm.py` (2)
- `venom_core/api/routes/system_storage.py`
- `venom_core/api/routes/tasks.py` (2)

#### C4. `venom_core/core/**`
- `venom_core/core/chronos.py` (2)
- `venom_core/core/dream_engine.py`
- `venom_core/core/energy_manager.py`
- `venom_core/core/hidden_prompts.py` (2)
- `venom_core/core/intent_manager.py` (2)
- `venom_core/core/model_manager.py` (5)
- `venom_core/core/model_registry.py`
- `venom_core/core/model_registry_clients.py`
- `venom_core/core/ota_manager.py`
- `venom_core/core/service_monitor.py`
- `venom_core/core/state_manager.py`
- `venom_core/core/streaming_handler.py`
- `venom_core/core/swarm.py`
- `venom_core/core/orchestrator/orchestrator_dispatch.py`
- `venom_core/core/orchestrator/session_handler.py` (2)
- `venom_core/core/flows/campaign.py`
- `venom_core/core/flows/code_review.py`

#### C5. `venom_core/execution/**`, `memory/**`, `services/**`, `spore/**`, frontend
- `venom_core/execution/kernel_builder.py`
- `venom_core/execution/model_router.py`
- `venom_core/execution/skill_manager.py`
- `venom_core/execution/skills/assistant_skill.py` (2)
- `venom_core/execution/skills/complexity_skill.py` (2)
- `venom_core/execution/skills/docs_skill.py` (2)
- `venom_core/execution/skills/file_skill.py`
- `venom_core/execution/skills/git_skill.py`
- `venom_core/execution/skills/huggingface_skill.py`
- `venom_core/execution/skills/parallel_skill.py`
- `venom_core/execution/skills/render_skill.py`
- `venom_core/execution/skills/test_skill.py` (2)
- `venom_core/main.py`
- `venom_core/memory/graph_rag_service.py` (3)
- `venom_core/memory/ingestion_engine.py` (2)
- `venom_core/memory/lessons_store.py`
- `venom_core/perception/desktop_sensor.py`
- `venom_core/perception/watcher.py`
- `venom_core/services/benchmark.py`
- `venom_core/services/config_manager.py`
- `venom_core/services/memory_service.py`
- `venom_core/services/runtime_controller.py`
- `venom_core/simulation/director.py`
- `venom_spore/main.py`
- `venom_spore/skill_executor.py`
- `web-next/components/brain/brain-home.tsx`
- `web-next/components/cockpit/cockpit-chat-send.ts`
- `web-next/components/cockpit/cockpit-request-detail-drawer.tsx`
- `web-next/components/layout/sidebar.tsx`
- `web-next/components/models/models-viewer.tsx`

### D. Nadmierne zagnieżdżenie (1)
- `web-next/tests/chat-context-icons.spec.ts` (L116)

## Strategia naprawy

### 1) Duplicated literals
- Wydzielenie stałych modułowych (UPPER_CASE) blisko miejsca użycia.
- Grupowanie stałych dla promptów/komunikatów wieloliniowych.
- Brak zmiany treści komunikatów (tylko deduplikacja).

### 2) Cognitive Complexity
- Zastosowanie guard clauses i early return.
- Ekstrakcja helperów pure (`parse_*`, `build_*`, `validate_*`, `map_*`).
- Dla route’ów API: rozdzielenie walidacji wejścia, logiki domenowej i mapowania odpowiedzi.
- Dla testów perf/e2e: ekstrakcja setupu scenariuszy i asercji do helperów.

### 3) Typing mismatch
- Dopasowanie argumentów do kontraktu funkcji (typy doubles / cast / fixture shape).
- Bez modyfikacji zachowania testów.

### 4) Frontend nesting
- Wyciągnięcie głęboko zagnieżdżonych callbacków do nazwanych helperów testowych.

## Plan batchy (proponowany)

1. `123-a`: duplicated literals (`examples/**`, `scripts/genesis.py`, wybrane `venom_core/**`, `venom_spore/**`) + typing mismatch (2 testy).
2. `123-b`: complexity w `tests/**` + `scripts/**` + frontend nesting (`web-next/tests/chat-context-icons.spec.ts`).
3. `123-c`: complexity w `venom_core/agents/**` + `venom_core/api/routes/**`.
4. `123-d`: complexity w `venom_core/core/**` + `execution/**` + `memory/**` + `services/**` + `venom_spore/main.py` + `web-next/components/**`.
5. `123-e`: finalny sweep, walidacja, aktualizacja statusu tasku i mapowanie issue->commit.

## Kryteria akceptacji

- [ ] Wszystkie 147 zgłoszeń z wsadu są zmapowane do commitów lub jawnie odroczone z uzasadnieniem.
- [ ] Brak otwartych `Critical` z tej listy po rescanu Sonar.
- [ ] Brak regresji testów/linta dla zmienionych obszarów.
- [ ] `mypy venom_core` i `ruff` przechodzą dla dotkniętego zakresu.
- [ ] Frontend lint przechodzi dla zmienionych komponentów/testów.

## Ryzyka

- Zbyt agresywna refaktoryzacja funkcji o dużej złożoności może zmienić zachowanie.
- Refaktoryzacja route’ów API może wpłynąć na kody odpowiedzi i kontrakt JSON.
- Testy perf/e2e po refaktorze helperów mogą stać się flaky bez stabilnej synchronizacji.

## Mitigacje

- Małe commity per plik/obszar i testy celowane po każdej grupie.
- Priorytet dla refaktorów strukturalnych bez zmiany logiki.
- Dodatkowe testy regresyjne tam, gdzie ekstrakcja helperów dotyka warunków biznesowych.

## Status realizacji (gałąź `feat/123-sonar-maintainability-batch`)

### Zrealizowane

- [x] `123-a` duplicated literals (`examples/**`, `scripts/genesis.py`, `venom_core/**`, `venom_spore/**`)
  - `e8acbd5` `refactor(sonar): extract duplicated literals in examples and scripts (123-a)`
  - `0380866` `refactor(sonar): extract duplicated literals in venom_core and venom_spore (123-a)`
- [x] `123-a` typing mismatch (2 testy)
  - `656ee75` `test(types): fix sonar typing mismatches in benchmark/helpers tests (123-a)`
- [x] `123-b` complexity `tests/**` + `tests/perf/**`
  - `3e05220` `refactor(tests): reduce cognitive complexity in test fixtures and perf scenarios (123-b)`
- [x] `123-b` complexity `scripts/**`
  - `17686d4` `refactor(scripts): reduce cognitive complexity in maintenance scripts (123-b)`
- [x] `123-b` frontend nesting (`web-next/tests/chat-context-icons.spec.ts`)
  - `5d75647` `refactor(web-next-tests): flatten nested callbacks in chat-context icons spec (123-b)`

### Walidacja wykonana lokalnie

- Python:
  - `.venv/bin/ruff check .` -> OK
  - `.venv/bin/mypy venom_core` -> OK
  - `pytest -q tests/test_benchmark_service_activation.py tests/test_helpers.py` -> `20 passed`
  - `pytest -q tests/conftest.py tests/perf/test_latency_modes_e2e.py tests/perf/test_llm_latency_e2e.py tests/perf/test_llm_simple_e2e.py` -> `3 passed`
- Frontend:
  - `npm --prefix web-next run lint` -> fail na artefakcie `web-next/coverage/lcov-report/block-navigation.js` (warning spoza zakresu zmian)
  - `npx eslint tests/chat-context-icons.spec.ts` (w `web-next/`) -> OK
  - `playwright test tests/chat-context-icons.spec.ts` -> fail środowiskowy (`page.goto('/')` bez poprawnego baseURL)

### W toku

- [x] `123-c`: complexity `venom_core/agents/**` + `venom_core/api/routes/**`
  - `26a2717` `refactor(api): reduce cognitive complexity in route handlers (123-c)`
  - `9bd85ce` `refactor(agents): reduce cognitive complexity in agent orchestration paths (123-c)`
  - `af52d00` `refactor(agents): reduce cognitive complexity in remaining specialist agents (123-c)`
  - `a6ff052` `refactor(api): reduce cognitive complexity in workflow and knowledge routes (123-c)`
  - `99fb8c8` `refactor(api): reduce cognitive complexity in memory and system routes (123-c)`
  - `0fb0807` `refactor(api): reduce cognitive complexity in remaining route handlers (123-c)`
- [x] `123-d`: complexity `venom_core/core/**` + `execution/**` + `memory/**` + `services/**` + `venom_spore/main.py` + `web-next/components/**`
  - `4c9e30b` `refactor(core): reduce cognitive complexity in entrypoint and model flows (123-d)`
  - `7f8b49d` `refactor(spore): reduce cognitive complexity in spore runtime executors (123-d)`
  - `d32a693` `refactor(core): reduce cognitive complexity in orchestration and state paths (123-d)`
  - `e14ed77` `refactor(execution): reduce cognitive complexity in kernel/router/skills orchestration (123-d)`
  - `1445d00` `refactor(memory-services): reduce cognitive complexity in memory and runtime services (123-d)`
  - `d64af72` `refactor(memory-services): reduce cognitive complexity in runtime controller flows (123-d)`
  - `b9bef66` `refactor(perception-sim): reduce cognitive complexity in sensors and simulation flows (123-d)`
  - `d4ff1bf` `refactor(web-next): reduce cognitive complexity in selected UI components (123-d)`
- [x] `123-e`: finalny sweep + pełne mapowanie issue->commit + statusy deferred

## Mapowanie issue -> commit (status closure)

### Fixed (w kodzie)

- `123-a`: duplicated literals + typing mismatch
  - `e8acbd5`, `0380866`, `656ee75`
- `123-b`: tests/scripts/frontend test nesting
  - `3e05220`, `17686d4`, `5d75647`
- `123-c`: agents + api routes
  - `26a2717`, `9bd85ce`, `af52d00`, `a6ff052`, `99fb8c8`, `0fb0807`
- `123-d`: core/execution/memory/services/spore/perception/simulation/web-next
  - `4c9e30b`, `7f8b49d`, `d32a693`, `e14ed77`, `1445d00`, `d64af72`, `b9bef66`, `d4ff1bf`

### Deferred (z uzasadnieniem)

Poniższe pozycje z `123_wsad.md` oznaczono jako `deferred` z powodu ryzyka regresji funkcjonalnej i/lub potrzeby osobnych, większych zmian architektonicznych, które wykraczają poza bezpieczny batch maintainability bez zmiany zachowania:

- `venom_core/agents/__init__.py`
- `venom_core/agents/architect.py`
- `venom_core/agents/coder.py`
- `venom_core/agents/documenter.py`
- `venom_core/agents/foreman.py`
- `venom_core/agents/ghost_agent.py`
- `venom_core/agents/operator.py`
- `venom_core/agents/professor.py`
- `venom_core/agents/release_manager.py`
- `venom_core/agents/shadow.py`
- `venom_core/agents/strategist.py`
- `venom_core/agents/system_status.py`
- `venom_core/agents/ux_analyst.py`
- `venom_core/core/chronos.py`
- `venom_core/core/dream_engine.py`
- `venom_core/core/energy_manager.py`
- `venom_core/core/flows/campaign.py`
- `venom_core/core/flows/code_review.py`
- `venom_core/core/hidden_prompts.py`
- `venom_core/core/intent_manager.py`
- `venom_core/core/model_registry.py`
- `venom_core/core/model_registry_clients.py`
- `venom_core/core/service_monitor.py`
- `venom_core/core/state_manager.py`
- `venom_core/core/streaming_handler.py`
- `venom_core/core/swarm.py`
- `venom_core/core/tracer.py`
- `venom_core/execution/kernel_builder.py`
- `venom_core/execution/skills/assistant_skill.py`
- `venom_core/execution/skills/complexity_skill.py`
- `venom_core/execution/skills/file_skill.py`
- `venom_core/execution/skills/git_skill.py`
- `venom_core/execution/skills/huggingface_skill.py`
- `venom_core/execution/skills/parallel_skill.py`
- `venom_core/execution/skills/render_skill.py`
- `venom_core/execution/skills/test_skill.py`
- `venom_core/main.py`
- `venom_core/memory/graph_rag_service.py`
- `venom_core/memory/ingestion_engine.py`
- `venom_core/perception/desktop_sensor.py`
- `venom_core/services/benchmark.py`
- `venom_core/services/config_manager.py`

Uwaga techniczna dla wsadu:
- wpisy `web-next/components/*/*.ts` w wsadzie odpowiadają komponentom `.tsx` i zostały pokryte commitami `123-d`.
