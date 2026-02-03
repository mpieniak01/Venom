# Krótki audyt krytycznych ścieżek: `venom_core/main.py` + `venom_core/core/dispatcher.py`

Data: 2026-01-31
Zakres: szybki przegląd ścieżek krytycznych (startup, zależności, dispatch/routing, zdalne wykonanie).

## 1) `venom_core/main.py` — krytyczne ścieżki

### Najważniejsze przepływy
- **Startup (`lifespan`)**: inicjalizacja tracer/monitorów, orchestratora, store’ów (session, state, vector, graph), background scheduler, watcher, audio/iot, shadow, node manager, router dependencies.
- **Wymuszenie LLM ready**: asynchroniczny `ensure_local_llm_ready()` z korektą modelu i próbą startu runtime.
- **Router dependencies**: ustawianie zależności dla endpointów (możliwy wpływ na 503/500 przy niepełnej inicjalizacji).

### Findings
**[MED] Shadow Agent actions są “no-op” i mimo to emitują zdarzenia**
- `handle_shadow_action()` zawiera TODO dla realnych akcji (error_fix / code_improvement / task_update). W praktyce generuje powiadomienia “action triggered” bez wykonania.
- **[ZREALIZOWANE]** Zmieniono komunikat na dynamiczny (i18n): "Shadow Agent: znalazł problem i sugeruje naprawę".

**[MED] BackgroundScheduler rejestruje zadania oznaczone jako PLACEHOLDER**
- `consolidate_memory` i `check_health` rejestrowane jako placeholder, co może sugerować funkcjonalność, której brak.
- **[ZREALIZOWANE]** Zmieniono status na "Coming Soon" (Localized) – zarówno w logach backendu, jak i w deskryptorach przekazywanych do UI.

**[LOW] `setup_router_dependencies()` wywoływane wielokrotnie**
- Funkcja ustawia `system_deps` dwukrotnie (z i bez `orchestrator`). Nie wygląda na krytyczny błąd, ale jest redundancja.

**[LOW] Tryb testowy inicjalizuje orchestratora bez pełnego lifespanu**
- Może maskować problemy z inicjalizacją zależności w testach w porównaniu do realnego startu.

### Rekomendacje (krótkie)
- Dla Shadow Agent: oznaczyć akcje jako “preview/placeholder” w UI albo blokować, dopóki nie ma integracji.
- Dla BackgroundScheduler: rozważyć feature-flag lub jasne oznaczenie w UI/logach, że joby są no-op.

---

## 2) `venom_core/core/dispatcher.py` — krytyczne ścieżki

### Najważniejsze przepływy
- **`dispatch()`**: routing po intencji, obsługa `generation_params`, delegacja do agentów.
- **Zdalne wykonanie**: `_dispatch_to_node()` i `node_manager.execute_skill_on_node()`.
- **`parse_intent()`**: regex + LLM fallback dla wyciągania akcji i ścieżek.

### Findings
**[HIGH] Brak fallbacku lokalnego przy błędzie zdalnego węzła**
- Jeśli `_dispatch_to_node()` rzuci wyjątek (np. błąd wykonania), `dispatch()` re-raise i nie przełącza się na lokalne wykonanie.
- **[ZREALIZOWANE]** Zgodnie z decyzją architektoniczną usunięto logikę fallbacku lokalnego. System rzuca błąd, gdy zdalne wykonanie zawiedzie.

**[MED] `_prepare_skill_parameters()` dla `FileSkill` zwraca `{}` (TODO)**
- Przy przekierowaniu do węzła brak wymaganych parametrów → potencjalny błąd wykonania.
- **[ZREALIZOWANE]** Zaimplementowano podstawowe parsowanie parametru `path` (regex) w `_prepare_skill_parameters`.

**[MED] `parse_intent()` LLM fallback bez walidacji schematu**
- JSON z LLM jest parsowany “na wiarę”. Błędny format = wyjątek → fallback do regex, ale bez walidacji typów.
- **[ZREALIZOWANE]** Dodano walidację zwróconej akcji (musi być w `ACTION_KEYWORDS` lub `unknown`). Dodano fallback przy błędzie parsowania.

**[LOW] `kernel.get_service()` bez jawnego wskazania serwisu**
- Jeśli kernel ma wiele serwisów, wybór domyślny może być niejednoznaczny.

### Rekomendacje (krótkie)
- Dodać możliwość **lokalnego fallbacku** po błędzie zdalnego węzła (z logiem warning).
- Uzupełnić `_prepare_skill_parameters()` dla `FileSkill` albo blokować zdalne wykonanie, gdy brak parametrów.
- Dodać walidację JSON z LLM (np. schema check + defensywne typy).

---

## 3) Co jest “na już” do decyzji - **[ZADECYDOWANO]**
- **Zdalne wykonanie**: Jeśli wykonanie na węźle zawiedzie, zadanie ma nie być wykonywane lokalnie (brak fallbacku).
- **Shadow Agent**: Zmieniono komunikat na: "znalazł problem i sugeruje naprawę".
- **Scheduler**: Status zadań placeholderowych zmieniono na "Coming Soon".

---

## 4) Zakres zmian do recenzji (Implementation Summary)

W ramach audytu 100 wprowadzono następujące zmiany:

### Backend (Python)
- **`venom_core/core/dispatcher.py`**:
    - Usunięcie fallbacku lokalnego w `dispatch()`.
    - Implementacja `_prepare_skill_parameters` dla `FileSkill` (podstawowe wyciąganie `path`).
    - Walidacja intencji z LLM (`parse_intent`).
- **`venom_core/main.py`**:
    - Przejście na klucze lokalizacji (`common.comingSoon`, `shadowActions.foundProblem`) zamiast statycznych tekstów.

### Frontend (TypeScript/React)
- **`web-next/lib/i18n/locales/[pl|en|de].ts`**: Dodanie nowych kluczy i18n i ujednolicenie statusów.
- **`web-next/components/cockpit/log-entry.tsx`**: Implementacja dynamicznych tłumaczeń dla komunikatów telemetrii (`t(payload.message)`).
- **`web-next/components/layout/command-center.tsx`**: Implementacja tłumaczeń dla statusów i opisów usług systemowych.
- **`web-next/lib/logs.ts`**: Rozszerzenie typu `LogPayload` o pole `data` (poprawka linta i wsparcie parametrów w i18n).
