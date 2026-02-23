# PR 172: Light Coverage Wave dla najsłabiej pokrytych plików

## Cel
- Podnieść coverage przez **lekkie testy jednostkowe** dla plików o najniższym pokryciu.
- Domknąć zmianę tak, aby przechodziła bramki jakości:
  - `make pr-fast`
  - `make check-new-code-coverage`

## Zasady wykonania (dla agenta kodowania)
- Skupiaj się na testach typu unit / pure logic.
- Nie dodawaj testów `requires_docker`, `requires_docker_compose`, `performance`, `smoke`.
- Preferuj dopisywanie testów do istniejących lekkich plików testowych.
- Każda fala kończy się lokalnym uruchomieniem:
  - `make pr-fast`
  - `make check-new-code-coverage`
- Jeśli bramka nie przechodzi, popraw testy i uruchom ponownie obie komendy.

## Priorytety (ROI)
1. Pliki 0% i bardzo małe/średnie:
   - `venom_core/execution/skills/chrono_skill.py`
   - `venom_core/agents/creative_director.py`
   - `venom_core/agents/designer.py`
   - `venom_core/agents/devops.py`
   - `venom_core/core/orchestrator.py`
   - `venom_core/nodes/protocol.py`
2. Pliki niskie 10-20% o wysokim wpływie:
   - `venom_core/core/scheduler.py`
   - `venom_core/api/model_schemas/model_validators.py`
   - `venom_core/core/flows/issue_handler.py`
   - `venom_core/memory/graph_store.py`
   - `venom_core/learning/dataset_curator.py`
3. Pliki z niskim coverage, ale duże:
   - `venom_core/services/translation_service.py`
   - `venom_core/infrastructure/docker_habitat.py`
   - `venom_core/main.py`
   - `venom_core/agents/analyst.py`
   - `venom_core/agents/strategist.py`
   - `venom_core/agents/ux_analyst.py`

## Plan fal
### Fala A (szybkie zwycięstwa)
- Dodać testy dla małych plików 0% (listy z Priorytetu 1).
- Cel: szybkie podniesienie globalnego trendu i liczby plików >0%.

### Fala B (stabilizacja kontraktów i schematów)
- Dodać testy wejść/wyjść i walidacji dla:
  - `model_validators.py`
  - `nodes/protocol.py`
  - `chrono_skill.py`
- Cel: pokrycie warunków i edge-case bez ciężkich zależności.

### Fala C (scheduler / workflow / memory)
- Dodać testy ścieżek decyzyjnych i błędów dla:
  - `core/scheduler.py`
  - `core/flows/issue_handler.py`
  - `memory/graph_store.py`
  - `learning/dataset_curator.py`
- Cel: podniesienie coverage linii i warunków w logice backendowej.

### Fala D (duże moduły z największą luką)
- Testy celowane na fragmenty o największej luce:
  - `services/translation_service.py`
  - `infrastructure/docker_habitat.py`
  - `main.py`
  - `agents/analyst.py`, `agents/strategist.py`, `agents/ux_analyst.py`
- Cel: domknięcie braków new-code i stabilizacja wyniku Sonar.

## Minimalny zakres testów na plik
- 1 test ścieżki pozytywnej.
- 1 test ścieżki błędu/fallback.
- 1 test edge-case (np. puste wejście, brak configu, nieprawidłowy typ).

## Definition of Done
- Wszystkie testy dodane w ramach fali przechodzą.
- `make pr-fast` = PASS.
- `make check-new-code-coverage` = PASS.
- W podsumowaniu PR:
  - lista dodanych testów,
  - status obu bramek,
  - changed-lines coverage,
  - ryzyka/obszary odłożone do następnej fali.

## Notatka operacyjna
- Jeśli Sonar nadal pokazuje stare luki po merge, zweryfikować:
  - zakres „New Code since …”,
  - czy testy są uruchamiane w lekkim zestawie Sonar,
  - czy coverage XML pochodzi z aktualnego runu.
