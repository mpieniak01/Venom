# Raport 104: Analiza gałęzi 103_translations_continuation

Data analizy: 2026-02-01

## 1. Streszczenie wykonawcze
Gałąź `103_translations_continuation` zawiera **1 commit względem `main`** (SHA: `5ddc190`) + **niezacommitowane zmiany** w backendzie i testach. Zakres wyszedł daleko poza zadanie 103 (i18n). Wprowadzono m.in. animacje i przebudowę UI Cockpitu, zmiany w „Brain” (wizualizacja grafu pamięci), modyfikacje API (aliasy dla pruning, mock grafu, testowe obejścia DI), oraz zmianę nazw itemów w API storage. To powoduje zamieszanie zakresowe oraz ryzyko regresji i w testach, i w semantyce API.

Ważne: zadanie 103 w `docs_dev/_to_do/103_tlumaczenie_i18n.md` opisuje głównie **i18n/ekstrakcję stringów/termínologię DE**, a obecny stan gałęzi miesza to z refaktorem pamięci/brain/knowledge oraz poprawkami testów.

## 2. Stan gałęzi i zakres zmian

### 2.1. Commit względem `main`
Commit: `5ddc190` — „feat: i18n fixes, cockpit animations, hydration fix”

Kluczowe obszary:
- i18n: masywne zmiany w `web-next/lib/i18n/locales/{pl,en,de}.ts` i powiązanych komponentach.
- UI: duże zmiany w `web-next/components/cockpit/*`, `web-next/components/brain/*`, `web-next/components/layout/*`.
- Backend: drobne zmiany w `venom_core/api/routes/system_storage.py` (nazwy itemów storage) i `venom_core/core/model_registry_clients.py` (follow_redirects).

### 2.2. Zmiany niezacommitowane (working tree)
Pliki modyfikowane lokalnie:
- Backend + testy: `venom_core/api/dependencies.py`, `venom_core/api/routes/memory.py`, `venom_core/api/routes/knowledge.py`, `venom_core/api/routes/learning.py`, `venom_core/main.py`, `tests/*`.
- UI: usunięcia nieużywanych hooków i drobne korekty w `web-next/components/*`.

Te zmiany **nie są** częścią commita 5ddc190, ale wpływają na całościowy stan gałęzi.

## 3. Zgodność z zadaniem 103 (i18n)

### Co jest zgodne z 103 (plusy)
- Rozbudowane tłumaczenia w `web-next/lib/i18n/locales/pl.ts`, `web-next/lib/i18n/locales/en.ts`, `web-next/lib/i18n/locales/de.ts`.
- Dodana obsługa lokalizacji w `dayjs` w `web-next/lib/i18n/index.tsx` (locale + relativeTime), co poprawia zgodność z i18n dla dat i czasu.
- Wiele komponentów UI przestawionych na `t()` (szczególnie Cockpit/Brain/Config), co realizuje założenie „zero hard-coded strings”.

### Co jest poza zakresem 103 (minusy)
- Zmiany w logice UI (animacje, layout, interakcje w Cockpit/Brain).
- Zmiany API w `system_storage.py` (zmiana nazw itemów), które nie są stricte i18n.
- Zmiany klienta HTTP (`follow_redirects=True`) w `model_registry_clients.py`.
- Zmiany w backendzie i testach dotyczące memory/knowledge/learning (aliasy, testowe DI, fallbacki).

**Wniosek:** Gałąź nie jest „czystą” kontynuacją zadania 103 i wymaga rozdzielenia zakresu.

## 4. Zmiany i ich skutki (szczegółowo)

### 4.1. i18n i UI (web-next)
**Dobre:**
- Przejście wielu komponentów na `t()` i dopasowanie kluczy.
- Lokalizacja dat (dayjs) spójna z wybraną językową konfiguracją.
- Uporządkowanie danych i tłumaczeń w `locales/*` (większa kompletność).

**Ryzyka / wątpliwości:**
- Dodatkowe zmiany w UI (animacje, layout, reorganizacja sekcji) zwiększają ryzyko regresji funkcjonalnych i utrudniają review i18n.
- Kilka komponentów ma usunięte `useTranslation()` bez pełnej weryfikacji, czy teksty pozostają w i18n (np. `web-next/components/brain/cache-management.tsx`, `web-next/components/brain/file-analytics.tsx`, `web-next/components/cockpit/cockpit-metrics.tsx`). To wygląda jak „cleanup”, ale trzeba potwierdzić, że nie wracamy do hardcoded strings.

### 4.2. API system_storage: zmiana nazw itemów
Plik: `venom_core/api/routes/system_storage.py`

**Zmiana:** Zmieniono nazwy itemów z opisowych PL na „klucze” (np. `Modele LLM` → `llm_models`, `Dane: memory` → `memory`).

**Skutek:** UI musi teraz tłumaczyć te wartości lub mapować je na i18n. Jeżeli UI nadal wyświetla `name` bez mapowania, to zmiana **zabiera lokalizację** i może zepsuć testy e2e/snapshoty (spodziewające się polskich opisów).

**Ocena:** zmiana nie jest zła sama w sobie, ale wymaga **konsekwentnej refaktoryzacji w UI** (najlepiej `name` jako klucz i18n, a nie tekst do wyświetlenia).

### 4.3. Memory/Brain/Knowledge — rozmycie odpowiedzialności

Pliki:
- `venom_core/api/routes/memory.py`
- `venom_core/api/routes/knowledge.py`
- `venom_core/api/routes/learning.py`

**Zmiany:**
- Dodano aliasy w `memory.py` przekierowujące pruning/learning do `/knowledge/...`.
- `knowledge.py` ma nowe helpery i limity mock grafu.
- `memory.py` robi fallback na różne kształty LessonsStore i buduje dane dla grafu w bardziej „tolerancyjny” sposób.

**Ryzyko:**
- API zaczyna mieszać pojęcia: „memory” obsługuje część „knowledge” i „learning”. W praktyce to „zatyczki kompatybilności”, ale bez jasnego komunikatu i docelowej koncepcji. To jest dokładnie ten „chaos koncepcyjny”, o którym wspomniałeś.

**Ocena:**
- Dobre: aliasy mogą uratować zgodność wsteczną (jeśli UI już woła memory endpointy).
- Złe: brak jasnej mapy „co jest canonical”, brak deprecations, brak dokumentacji i testów kontraktu.

### 4.4. Dependency Injection i testy
Pliki:
- `venom_core/api/dependencies.py`
- `venom_core/main.py`
- `tests/test_api_dependencies.py`, `tests/test_memory_api.py`, `tests/api/test_memory_api_pruning.py`

**Zmiany:**
- `dependencies.py` automatycznie inicjalizuje globalne serwisy w trybie testowym (`PYTEST_CURRENT_TEST`).
- Testy przestawione na `app.dependency_overrides` zamiast globalnych set_*.

**Dobre:**
- Czyszczenie cache w set_* funkcjach.
- `dependency_overrides` to poprawny, idiomatyczny sposób w FastAPI.

**Złe / ryzyka:**
- Auto-inicjalizacja w `dependencies.py` może **maskować** błędy w testach (brak jawnej konfiguracji). Testy przechodzą, ale produkcja może nadal padać przy braku init.
- W `get_orchestrator()` jest podwójny `global _orchestrator` (drobny bug kosmetyczny).
- `main.py` inicjalizuje storage w trybie testowym bez lifespan — to „zatyczka”, która może być ok w testach, ale **nie powinna mieszać się z logiką runtime**.

### 4.5. Wyniki testów
Uruchomione testy (lokalnie):
- `pytest tests/test_api_dependencies.py tests/test_memory_api.py tests/api/test_memory_api_pruning.py -q`
- Wynik: `6 passed, 1 skipped` (ok)

Nie zostały uruchomione:
- E2E (`make e2e`), testy UI/snapshoty, pełny `pytest`.

## 5. Co jest dobre, co złe, co do poprawy

### Dobre
- i18n w UI jest w dużej mierze „dociągnięte” (rozszerzone locale i użycie `t()` w wielu komponentach).
- W `dayjs` ustawiona lokalizacja zgodnie z językiem — to było luką w 103.
- Pojawiają się aliasy API (intencja kompatybilności wstecznej) — to minimalizuje breaky w runtime.
- Testy pamięci są doprowadzane do stabilnego wzorca (dependency overrides, cleanup fixtures).

### Złe
- Zakres znacznie wykracza poza zadanie 103; brak czystego review i „scope creep”.
- Mieszanie terminologii: memory vs brain vs knowledge vs learning (API i UI używają się naprzemiennie).
- Zmiana `system_storage` na nienaturalne „klucze” bez pełnego mapowania w UI.
- Ukryte „testowe” zachowania w `dependencies.py` i `main.py` — testy mogą nie wykrywać błędów inicjalizacji.

### Do poprawy (konkretne działania)
1. **Rozdzielić zakres**: osobny PR/commit dla i18n, osobny dla UI/animacji, osobny dla zmian w backend/testach.
2. **Zdefiniować koncepcję**: czy „Brain” to UI warstwa „Memory/Knowledge” czy nowy system? Ustalić canonical API (`/knowledge` vs `/memory`) i jawnie ogłosić deprecations.
3. **Storage API**: jeśli `name` to klucz, to **mapować w UI** na i18n (np. `storage.items.llm_models`). Jeżeli `name` to „label”, to wrócić do lokalizowanych opisów.
4. **DI w testach**: zostawić tylko `dependency_overrides` (fixture), a auto-init w `dependencies.py` ograniczyć lub usunąć (ew. przełączyć na jawne `TESTING_MODE` w config).
5. **Testy E2E/UI**: sprawdzić czy nowe animacje i layout w Cockpit/Brain nie rozbijają testów wizualnych lub selektorów.

## 6. Rekomendowana ścieżka „co dalej”

Opcja A (najbezpieczniejsza):
- Rebase/odtworzyć gałąź jako „czyste” i18n: tylko zmiany w `locales/*`, `i18n/index.tsx` i komponentach, które **wyłącznie** przekładają stringi na `t()`.
- Wszelkie zmiany backend/UI przenieść do osobnych gałęzi.

Opcja B (szybka stabilizacja):
- Dodać dokument `docs_dev/decisions/brain-memory-knowledge.md` z jasną mapą pojęć i API.
- W `system_storage` podnieść do i18n mappingu w UI.
- Usunąć „testowe fallbacki” z produkcyjnych ścieżek (przenieść do fixture/override).

## 7. Lista plików do uważnego review (priorytet)
- `web-next/lib/i18n/locales/pl.ts`
- `web-next/lib/i18n/locales/en.ts`
- `web-next/lib/i18n/locales/de.ts`
- `web-next/components/brain/brain-home.tsx`
- `web-next/components/cockpit/*`
- `venom_core/api/routes/system_storage.py`
- `venom_core/api/dependencies.py`
- `venom_core/api/routes/memory.py`
- `venom_core/api/routes/knowledge.py`
- `tests/test_memory_api.py`


## 8. Zamknięcie zadania 103 i przeniesienie dalszych prac do 104

### 8.1. Co zostało zrobione w ramach 103 (stan faktyczny gałęzi)
Na gałęzi `103_translations_continuation` zostały wprowadzone zmiany, które w praktyce domykają wymagania i18n z zadania 103, ale z dużym nadmiarem zakresu.

**Zrealizowane elementy i18n (zgodne z 103):**
- Rozszerzone i zsynchronizowane locale w `web-next/lib/i18n/locales/{pl,en,de}.ts`.
- Dodane ustawianie locale w `dayjs` w `web-next/lib/i18n/index.tsx` (w tym `relativeTime`).
- Użycie `t()` w wielu komponentach UI (Cockpit/Brain/Config).

**Dodatkowy zakres (nie był celem 103, ale znalazł się na gałęzi):**
- Rozbudowa i modyfikacje UI Cockpitu i Brain (layout, animacje, przepływy).
- Zmiany w API i backendzie: `system_storage.py`, `model_registry_clients.py`, aliasy pruning/learning, fallbacki testowe.
- Zmiany w testach (dependency overrides, test fixtures).

### 8.2. Decyzja projektowa
- **Zadanie 103 uznajemy za zamknięte.**
- **Dalsze prace oraz porządkowanie zakresu kontynuujemy w ramach dokumentu 104.**
- **Gałęzi nie zmieniamy** (pozostajemy na `103_translations_continuation`), ale wszystkie nowe decyzje i korekty zakresu są opisywane w 104.

### 8.3. Stan odniesienia (branch + commit)
- Gałąź: `103_translations_continuation`
- Commit względem `main`: `5ddc190` („feat: i18n fixes, cockpit animations, hydration fix”)
- Zmiany niezacommitowane: backend + testy + drobne UI cleanup (lista w sekcji 2.2)

### 8.4. Co dalej (kontynuacja w 104)
- Rozdzielenie zakresu i18n vs UI vs backend.
- Ustalenie spójnej koncepcji memory/brain/knowledge.
- Uporządkowanie API storage (mapowanie na i18n lub powrót do opisowych nazw).

## 9. Progres prac (log 104)

### 2026-02-01
- Potwierdzono status gałęzi: `103_translations_continuation` (niezmieniana).
- Testy pełne `pytest -q` oraz wariant light `pytest -q -n 0 -m "not performance" -k "not browser_skill and not skills_enhancements and not forge_integration"` **timeout po 120s**.
- Testy zakresu pamięci/API: `pytest -q tests/test_api_dependencies.py tests/test_memory_api.py tests/api/test_memory_api_pruning.py` **przechodzą** (6 passed, 1 skipped).

Wnioski:
- Stabilizacja testów wymaga podziału uruchomień (light/long/heavy) lub zwiększenia timeoutu.
- Na teraz potwierdzona jest poprawność testów dotykających zmian w `dependencies/memory`.

### 2026-02-01 (pomiary light + durations)
Pomiary wykonane dla listy `config/pytest-groups/light.txt` z wyłączeniem testów z brakującymi zależnościami (asyncssh/pyperclip/arq/bleach). Komenda:
`rg -v "test_cloud_provisioner|test_desktop_sensor|test_desktop_sensor_roi|test_foreman_agent|test_message_broker|test_ota_manager|test_parallel_skill|test_render_skill" config/pytest-groups/light.txt | xargs pytest -q -n 0 --durations=30`

Wynik:
- Czas: **138.30s**
- Status: **12 failed, 1538 passed, 97 skipped**

Najwolniejsze testy (top 10 z `--durations=30`):
- 12.03s `tests/test_watcher.py::test_watcher_callback_triggered`
- 9.12s `tests/test_session_summary_llm.py::test_summary_uses_llm_when_available`
- 5.03s `tests/test_hardware_bridge.py::TestHardwareBridgeHTTP::test_connect_http_unreachable`
- 4.80s `tests/test_core_nervous_system.py::test_multiple_tasks_concurrent`
- 4.38s `tests/test_core_nervous_system.py::test_get_all_tasks` (setup)
- 4.18s `tests/test_core_nervous_system.py::test_get_task` (setup)
- 4.15s `tests/test_core_nervous_system.py::test_invalid_task_request` (setup)
- 4.14s `tests/test_core_nervous_system.py::test_get_nonexistent_task` (setup)
- 4.13s `tests/test_core_nervous_system.py::test_create_task` (setup)
- 3.54s `tests/test_ghost_agent.py::TestGhostAgent::test_process_notepad_task`

Dodatkowo zauważalnie wolne (~3s):
- `tests/test_orchestrator_intent.py::test_orchestrator_different_intents` (3.03s)
- `tests/test_session_summary_llm.py::*` (2.99s, 3.02s)
- `tests/test_dream_engine.py::test_enter_rem_phase_no_knowledge` (2.83s)

Failing testy (przyczyny środowiskowe / brak zależności):
- `tests/test_gpu_habitat.py` (7 testów) — `docker` = None (brak klienta dockera w module)
- `tests/test_lessons_governance.py::test_toggle_learning_updates_settings` — brak `config_manager` w `venom_core.api.routes.memory`
- `tests/test_recorder.py` (4 testy) — brak `pynput` i `mss` → listener/screenshot nie działa

Wnioski i decyzje do podjęcia:
1) **Przeniesienie wolnych testów** z `light` do `long` (np. `test_watcher.py`, `test_session_summary_llm.py`, `test_hardware_bridge.py`, `test_core_nervous_system.py`, `test_ghost_agent.py`, `test_dream_engine.py`).
2) **Ustalenie polityki zależności opcjonalnych**: czy instalujemy brakujące pakiety (asyncssh, pyperclip, arq, bleach, pynput, mss, docker) czy oznaczamy testy jako skipped bez tych deps.
3) **Naprawa regresji**: `test_lessons_governance.py` — brak `config_manager` w `memory.py` (prawdopodobnie efekt zmian w 103/104).

### 2026-02-01 (stabilizacja testów + decyzje)
- Przestawiono kolejność w `config/pytest-groups/light.txt`, aby najdłuższe testy startowały najwcześniej (na początek listy). Dotyczy: `test_watcher`, `test_session_summary_llm`, `test_hardware_bridge`, `test_core_nervous_system`, `test_ghost_agent`, `test_orchestrator_intent`, `test_dream_engine`.
- Zależności brakujące w środowisku zostały zainstalowane w `.venv` (asyncssh, pyperclip, arq, bleach, pynput, mss, docker). Wymagania już były wpisane w `requirements.txt` — nie dodawano nowych pozycji.
- Naprawiono regresję testu `test_lessons_governance.py` przez przywrócenie `config_manager` w `venom_core/api/routes/memory.py` (zgodność wsteczna testów).
- Smoke re-test: `.venv/bin/pytest -q tests/test_lessons_governance.py::test_toggle_learning_updates_settings tests/test_gpu_habitat.py::test_generate_training_script tests/test_recorder.py::TestDemonstrationRecorder::test_listeners_started` → **3 passed**.

Uwaga dot. MCP:
- `mcp>=1.0.0` pozostaje w `requirements.txt` i jest wymagane, ponieważ działa już mechanizm proxy MCP (będzie dalej rozwijany).

### 2026-02-01 (fix: test_core_nervous_system flakiness)
- Naprawiono flaka w `tests/test_core_nervous_system.py::test_multiple_tasks_concurrent` (STATUS: PROCESSING vs COMPLETED) przez polling i przejście na `TestClient` (sync), który uruchamia lifespan i inicjalizuje orchestrator. Usunięto zależność od `AsyncClient` bez lifespan.
- Smoke test: `.venv/bin/pytest -q tests/test_core_nervous_system.py::test_multiple_tasks_concurrent` → **passed** (30.63s).

### 2026-02-01 (E2E: diagnoza wstępna + poprawka SSE/context)
- Zidentyfikowano 9 failingów E2E (chat-context-icons, chat-mode-routing, smoke, streaming). Wspólny trop: EventSource/SSE payload w testach jest obiektem JS, a parser w `use-task-stream` obsługiwał wyłącznie string JSON.
- Poprawka: `safeParse` w `web-next/hooks/use-task-stream.ts` przyjmuje teraz `unknown` i zwraca obiekt, jeśli `data` jest już obiektem (bez JSON.parse). Powinno to przywrócić `context_used` (ikony 🎓/🧠) i stabilizować SSE w testach.
- Do weryfikacji: rerun `npm --prefix web-next run test:e2e:functional` po poprawce.

### 2026-02-01 (E2E: naprawy smoke i język)
- Dodano `venom-language=pl` w `web-next/tests/smoke.spec.ts` (beforeEach), aby testy były deterministyczne językowo i nie zależały od locale przeglądarki.
- Po tej zmianie zestaw smoke przechodzi: `npm --prefix web-next run test:e2e:functional -- --workers=1 --grep "Venom Next Cockpit Smoke"` → **23 passed**.

### 2026-02-01 (E2E: stabilizacja chat-mode/context/streaming)
- Dodano znacznik hydracji (`document.documentElement.dataset.hydrated = "true"`) w `LanguageProvider` i ustawienie `venom-language=pl` w testach E2E (chat-mode-routing, chat-context-icons, streaming), plus oczekiwanie na hydrację przed interakcjami.
- Efekt: testy SSE/Chat Mode przestały flakować w trybie równoległym.
- Re-test: `npm --prefix web-next run test:e2e:functional -- --workers=4 --grep "Chat context icons|Chat mode routing|Cockpit streaming SSE"` → **7 passed**.

### 2026-02-01 (E2E: flake Awaryjne zatrzymanie)
- Zidentyfikowano flaka w `smoke.spec.ts` wynikającego z kliknięcia przed pełną hydracją (SSR bez handlerów). Dodano `waitForHydration` przed kliknięciem w teście "Awaryjne zatrzymanie kolejki".
- Re-test: `npm --prefix web-next run test:e2e:functional -- --workers=4 --grep "Awaryjne zatrzymanie"` → **passed**.
