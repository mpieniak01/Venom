# THE ARCHITECT - Planowanie Strategiczne i Orkiestracja Kroków

## Rola

Architect Agent jest warstwą planowania dla złożonych żądań w Venom.
Przekształca jeden cel użytkownika w wykonalny `ExecutionPlan`, a następnie orkiestruje wykonanie krok po kroku przez `TaskDispatcher`.

Implementacja główna: `venom_core/agents/architect.py`.

## Odpowiedzialności

- Strategiczna dekompozycja złożonych celów na konkretne kroki.
- Dobór właściwego wykonawcy dla każdego kroku.
- Wymuszanie kolejności przez `depends_on`.
- Przekazywanie kontekstu między krokami zależnymi.
- Składanie wyników kroków w końcowe podsumowanie wykonania.

## Wykonawcy i mapowanie intencji

Architect planuje kroki etykietami agentów i mapuje je na intencje dispatchera:

- `RESEARCHER` -> `RESEARCH`
- `CODER` -> `CODE_GENERATION`
- `LIBRARIAN` -> `KNOWLEDGE_SEARCH`
- `TOOLMAKER` -> `TOOL_CREATION`

Jeśli krok użyje nieznanej etykiety, fallback intent to `CODE_GENERATION`.

## Przepływ runtime

1. `IntentManager` klasyfikuje żądanie jako `COMPLEX_PLANNING`.
2. `TaskDispatcher` kieruje je do `ArchitectAgent` (`agent_map["COMPLEX_PLANNING"]`).
3. `ArchitectAgent.process(input_text)`:
   - wywołuje `create_plan(input_text)`,
   - potem `execute_plan(plan)`.
4. Architect wykonuje kroki przez `TaskDispatcher.dispatch(intent, content)`.
5. Wynik końcowy to skonsolidowany raport wykonania wszystkich kroków.

## Planowanie (`create_plan`)

`create_plan(user_goal)`:

1. Buduje historię rozmowy z `PLANNING_PROMPT` i celem użytkownika.
2. Wywołuje LLM przez `_invoke_chat_with_fallbacks`.
3. Oczekuje ścisłego JSON z `steps[]`.
4. Usuwa ewentualne markdown code fences z odpowiedzi.
5. Parsuje kroki do:
   - `ExecutionStep.step_number`
   - `ExecutionStep.agent_type`
   - `ExecutionStep.instruction`
   - `ExecutionStep.depends_on`
6. Zwraca `ExecutionPlan(goal, steps, current_step=0)`.

### Fallback planowania

Gdy parsowanie JSON lub samo planowanie się nie powiedzie:
- Architect zwraca minimalny plan awaryjny z 1 krokiem:
  - `step_number=1`
  - `agent_type="CODER"`
  - `instruction=user_goal`

To utrzymuje ciągłość wykonania, ale redukuje specjalizację.

## Wykonanie (`execute_plan`)

`execute_plan(plan)` działa sekwencyjnie:

1. Weryfikuje, że `task_dispatcher` jest ustawiony (`set_dispatcher` podczas inicjalizacji).
2. Iteruje po krokach w kolejności.
3. Dla każdego kroku:
   - opcjonalnie emituje `PLAN_STEP_STARTED`,
   - buduje kontekst kroku,
   - dispatchuje do zmapowanej intencji,
   - zapisuje wynik (`step.result` i lokalne `context_history`),
   - dopisuje sekcję do podsumowania końcowego,
   - opcjonalnie emituje `PLAN_STEP_COMPLETED`.
4. Przy wyjątku w kroku:
   - loguje błąd,
   - dopisuje sekcję błędu do podsumowania,
   - przechodzi do kolejnych kroków.

### Kontekst zależności

Gdy `depends_on` wskazuje zakończony krok:
- Architect dokleja wynik poprzedniego kroku jako kontekst.
- Kontekst zależności jest przycinany do 1000 znaków.

## Eventy broadcast

Jeśli skonfigurowany jest `event_broadcaster`, Architect emituje:

- `PLAN_CREATED`
- `PLAN_STEP_STARTED`
- `PLAN_STEP_COMPLETED`

To jest opcjonalne i nie blokuje głównego wykonania.

## Kontrakt danych (ExecutionPlan)

Zdefiniowany w `venom_core/core/models.py`:

- `ExecutionPlan.goal: str`
- `ExecutionPlan.steps: list[ExecutionStep]`
- `ExecutionPlan.current_step: int`

Pola `ExecutionStep`:

- `step_number: int`
- `agent_type: str`
- `instruction: str`
- `depends_on: int | None`
- `result: str | None`

## Ograniczenia

- Tylko wykonanie sekwencyjne (brak równoległego scheduler'a kroków w Architect).
- Brak walidacji strukturalnej cykli w `depends_on`.
- Brak automatycznej naprawy planu po częściowych błędach.
- Fallback do pojedynczego kroku CODER może ukrywać problemy jakości planowania.

## Konfiguracja

Architect nie wymaga dedykowanych flag w `.env`.
Działanie zależy od:

- dostępności/konfiguracji LLM dla chat service w Kernelu,
- poprawnego spięcia dispatchera (`TaskDispatcher` + `set_dispatcher`),
- opcjonalnej konfiguracji event broadcastera.

## Powiązane dokumenty

- `docs/PL/CHAT_SESSION.md` - tryby routingu i ścieżka Complex.
- `docs/PL/THE_CODER.md` - warstwa wykonawcza kodu.
- `docs/PL/THE_RESEARCHER.md` - rola wykonawcy research.
- `docs/PL/THE_INTEGRATOR.md` - workflow issue-to-PR z planowaniem.
