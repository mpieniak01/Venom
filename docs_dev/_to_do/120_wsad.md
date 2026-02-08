## 120 — WSAD Sonar (FastAPI HTTPException `responses`)

### Status realizacji

#### Zrealizowane
- [x] Batch `120-a` (commit `da8ebc8`): dodane `responses={...}` dla:
  - `venom_core/api/routes/agents.py`
  - `venom_core/api/routes/benchmark.py`
  - `venom_core/api/routes/calendar.py`
  - `venom_core/api/routes/feedback.py`
  - `venom_core/api/routes/flow.py`
  - `venom_core/api/routes/git.py`
  - `venom_core/api/routes/llm_simple.py`
  - `venom_core/api/routes/memory.py`
  - `venom_core/api/routes/memory_projection.py`
  - `venom_core/api/routes/models_install.py`

- [x] Batch `120-b` (commit `c3e496c`):
  - `venom_core/api/routes/models_usage.py`
  - `venom_core/api/routes/models_registry.py`
  - `venom_core/api/routes/models_registry_ops.py`
  - `venom_core/api/routes/models_translation.py`

- [x] Batch `120-c` (commit `5689162` + typowanie `839acaa`):
  - `venom_core/api/routes/system_*.py`
  - `venom_core/api/routes/tasks.py`
  - `venom_core/api/routes/queue.py`
  - `venom_core/api/routes/strategy.py`
  - `venom_core/api/routes/nodes.py`
  - `venom_core/api/routes/knowledge.py`

- [x] Batch `120-e` (commit `a217497`):
  - mikro-fix Sonar w `web-next/lib/env.ts` (`window` -> `globalThis.window` / `globalThis`)

- [x] Dodatkowy fix startu developerskiego (commit `e40985c`):
  - `Makefile`: `make start` nie próbuje uruchamiać drugiego backendu, jeśli API na `:8000` już działa.

- [x] Batch `120-d` (commit `f2389ac`):
  - `venom_core/api/routes/learning.py`
  - `venom_core/api/routes/system_iot.py`
  - `venom_core/api/routes/memory.py`
  - `venom_core/api/routes/knowledge.py` (`/lessons/learning/status`)

- [x] Batch `120-f` (commity `ac4af8a`, `2839f2c`, `7cb3e94`):
  - typing mismatch fixes w test doubles (`benchmark/dashboard/helpers/node_manager/swarm_wrapper`)
  - cleanup tautologicznych asercji i no-op callbacków w testach
  - runtime perf fix: `venom_core/memory/graph_rag_service.py` (`re.sub` -> `str.replace`)

#### Do domknięcia
- Brak otwartych pozycji implementacyjnych w zakresie tasku `120`.

#### Wycofane / nieaktualne
- Sekcja `W toku (120-c)` poniżej jest nieaktualna po commitach `5689162` i `839acaa`.

#### Kolejny krok
- Wykonać reskan Sonar i zamknąć ticket `120`.

---

### Rozszerzenie zakresu: Batch `120-f` (tests suspicious typing + hygiene)

#### Źródło
- Lista 46 zgłoszeń przekazana z Sonar (krytyczne `suspicious`, `typing`) + 1 runtime zgłoszenie perf regex.

#### Klasyfikacja i decyzje

1. `typing` mismatch (naprawa kodem, priorytet P1)
- `tests/test_benchmark_service_activation.py` (`_test_model` argument type)
- `tests/test_dashboard_api.py` (`ConnectionManager.connect/disconnect` argument type)
- `tests/test_helpers.py` (`write_file` argument type)
- `tests/test_node_manager.py` (`register_node` argument type)
- `tests/test_swarm_wrapper.py` (`create_venom_agent_wrapper` argument type)
- Decyzja:
  - Doprecyzować typy test doubles (`Protocol`/`cast`) albo dopasować fixture objects do oczekiwanych typów wejściowych.
  - Utrzymać semantykę testów bez zmian.

2. `identity check always true` (test-hygiene, priorytet P2)
- Pliki z listy:
  - `tests/test_component_engine.py`
  - `tests/test_council_basic.py`
  - `tests/test_designer_agent.py`
  - `tests/test_documenter.py`
  - `tests/test_external_discovery_integration.py`
  - `tests/test_graph_rag_service.py`
  - `tests/test_guardian_agent.py`
  - `tests/test_ingestion_engine.py`
  - `tests/test_memory.py`
  - `tests/test_oracle_agent.py`
  - `tests/test_persona_factory.py`
  - `tests/test_render_skill.py`
  - `tests/test_simulation_director.py`
  - `tests/test_stack_manager.py`
  - `tests/test_watcher.py`
- Decyzja:
  - Usunąć asercje tautologiczne (`obj is not None` dla klas/obiektów tworzonych lokalnie, `x is True/False` gdy Sonar wskazuje pewność wartości).
  - Zastąpić asercjami stanu/efektu (`assert x`, `assert not x`, `assert field == value`) tam, gdzie zwiększa to wartość testu.

3. Puste funkcje w testach (`pass`) (test-hygiene, priorytet P2)
- `tests/test_energy_manager.py` (dummy callback)
- `tests/test_translation_service.py` (dummy client init)
- Decyzja:
  - Dodać jawny komentarz uzasadniający no-op albo zastąpić krótką implementacją no-op (`return None`) dla czytelności.

4. Runtime perf smell (`re.sub` -> `str.replace`) (naprawa kodem, priorytet P1)
- `venom_core/memory/graph_rag_service.py` (linia ~125)
- Decyzja:
  - Zamienić `re.sub(r"```", "", sanitized_text)` na `sanitized_text.replace("```", "")` (to literal replacement, bez regex).

#### Plan commitów dla `120-f`
1. `test(sonar): fix suspicious typing mismatches in API/unit tests`
2. `test(sonar): remove tautological identity assertions in legacy tests`
3. `refactor(memory): replace regex literal cleanup with str.replace`
4. `docs(todo): update 120 wsad after batch 120-f`

#### Mikro-zakres (powiązane zgłoszenia Sonar, poza API `responses`)
- Zrealizowane:
  - `web-next/lib/env.ts`
    - L11: Prefer `globalThis.window` over `window`.
    - L12: Prefer `globalThis` over `window`.

### Notatka
- Celem jest wyłącznie uzupełnienie dokumentacji wyjątków FastAPI przez `responses={...}` bez zmiany logiki endpointów.

### Snapshot analizy (równolegle do 119)
- Aktualny skan route'ów: `66` dekoratorów `@router.*` bez `responses={...}`.
- Proponowane batchowanie dalszych prac:
  - `120-c` (system + orchestracja): `system_*`, `tasks.py`, `queue.py`, `strategy.py`, `nodes.py`, `knowledge.py`
  - `120-d` (pozostałe API): `learning.py`, `memory.py`, `system_iot.py` + ewentualne resztki po `120-c`
  - `120-e` (frontend micro-fix): `web-next/lib/env.ts` (`window` -> `globalThis.window` / `globalThis`)
- Zasada realizacji: commity `120` wyłącznie ścieżkami `venom_core/api/routes/*`, bez mieszania z refactorami `web-next` z `119`.

---

Na podstawie raportu z sonara dla zidentyfikowaliśmy kluczowe obszary kodu, które wymagają refaktoryzacji w celu poprawy czytelności, utrzymania i redukcji ryzyka regresji. Poniżej przedstawiamy plan działania, który obejmuje mapowanie hotspotów, priorytetyzację refaktorów oraz kryteria akceptacji.


venom_core/api/routes/agents.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L49
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L56
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L71
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L78
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L93
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L100
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L128
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L146
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L149
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L161
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/benchmark.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L89
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L105
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L108
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L136
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L144
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L154
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L175
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L185
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L203
5min effort
20 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L213
5min effort
20 days ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L232
5min effort
20 days ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L239
5min effort
20 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L248
5min effort
20 days ago
Code Smell
Major
venom_core/api/routes/calendar.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L76
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L142
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L168
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L171
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L206
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/feedback.py


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L54
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L57
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L60
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L99
5min effort
12 days ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L103
5min effort
12 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L124
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L193
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/flow.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L75
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L79
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/git.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L175
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L291
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L303
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L328
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 501 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L331
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L351
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 501 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L354
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/knowledge.py


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L508
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L529
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L556
5min effort
6 days ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L588
5min effort
6 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L605
5min effort
6 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L629
5min effort
6 days ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L645
5min effort
6 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L654
5min effort
6 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L667
5min effort
6 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L688
5min effort
6 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L707
5min effort
6 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L734
5min effort
6 days ago
Code Smell
Major
venom_core/api/routes/llm_simple.py


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L56
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L59
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/memory.py


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L170
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L208
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L211
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L233
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L258
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L261
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L275
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L306
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L308
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L334
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L569
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L575
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L591
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L599
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L653
5min effort
20 days ago
Code Smell
Major
venom_core/api/routes/memory_projection.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L38
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L42
5min effort
14 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L74
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/models_install.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L56
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L99
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L111
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L114
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L138
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L148
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L154
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L163
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L211
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L217
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L227
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L232
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L240
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L244
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L252
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/models_registry.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L32
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L42
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L74
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L84
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L90
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L111
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L125
5min effort
7 days ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L131
5min effort
7 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L152
5min effort
7 days ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L168
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L176
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L189
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/models_registry_ops.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L24
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L49
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L52
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L62
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L74
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L77
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L87
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L110
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L115
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L125
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L137
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L147
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L152
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L159
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/models_translation.py


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L26
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L44
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L47
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/models_usage.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L28
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L37
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L47
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L58
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L63
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/nodes.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L47
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L63
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L81
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L89
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L96
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L116
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L125
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L129
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 504 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L148
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L154
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/queue.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L37
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L48
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L65
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L74
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L91
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L100
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L117
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L128
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L145
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L153
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L174
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L180
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L191
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/strategy.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L41
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L116
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L134
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L148
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L163
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L173
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L188
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L204
5min effort
1 month ago
Code Smell
Major
venom_core/api/routes/system_config.py


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L25
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L45
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L59
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L79
5min effort
13 days ago
Code Smell
Major
venom_core/api/routes/system_governance.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L36
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L50
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L60
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L86
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L117
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L133
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L145
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L156
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L174
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L203
5min effort
13 days ago
Code Smell
Major
venom_core/api/routes/system_llm.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L49
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L106
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L127
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L130
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L172
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L175
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L178
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L180
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L239
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L241
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L245
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L259
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L353
5min effort
13 days ago
Code Smell
Major
venom_core/api/routes/system_metrics.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L54
5min effort
12 days ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L72
5min effort
12 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L111
5min effort
12 days ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L129
5min effort
12 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L138
5min effort
12 days ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L157
5min effort
13 days ago
Code Smell
Major
venom_core/api/routes/system_runtime.py


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L100
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L113
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L125
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L134
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L152
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L166
5min effort
13 days ago
Code Smell
Major
venom_core/api/routes/system_scheduler.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L20
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L29
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L39
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L48
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L58
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L67
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L77
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L86
5min effort
13 days ago
Code Smell
Major
venom_core/api/routes/system_services.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L23
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L54
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L64
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L72
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L81
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L104
5min effort
13 days ago
Code Smell
Major
venom_core/api/routes/system_status.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L21
5min effort
13 days ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L41
5min effort
13 days ago
Code Smell
Major
venom_core/api/routes/system_storage.py


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L91
5min effort
2 days ago
Code Smell
Major
venom_core/api/routes/tasks.py


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L154
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 500 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L166
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L186
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L190
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L207
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
MPieniak
MPieniak
L210
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L321
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L355
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 400 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L361
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 503 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L423
5min effort
1 month ago
Code Smell
Major


Document this HTTPException with status code 404 in the "responses" parameter.

Intentionality
Maintainability


4
High
documentation
fastapi
...
+
Open
Not assigned
L427
5min effort
1 month ago
Code Smell
Major


venom_core/memory/graph_rag_service.py


Replace this "re.sub()" call by a "str.replace()" function call.

Intentionality
Maintainability


4
High
performance
regex
+
Open
Not assigned
