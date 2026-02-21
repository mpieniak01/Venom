# THE SIMULACRUM - Simulation Layer

Status: Active (trimmed scope, 2026-02)

## Current scope

The `venom_core/simulation` package currently provides two runtime components:

1. `PersonaFactory` (`persona_factory.py`)
2. `ScenarioWeaver` (`scenario_weaver.py`)

These are used for synthetic user profiling and scenario generation.

## Removed components

The legacy `SimulationDirector` flow has been removed from runtime and tests.
If you still have old local scripts, migrate them to `PersonaFactory` + `ScenarioWeaver`.

## Quick start

### PersonaFactory

```python
from venom_core.simulation import PersonaFactory

factory = PersonaFactory(kernel=None)
persona = factory.generate_persona(goal="Zarejestrowac konto", archetype="senior")
print(persona.to_json())
```

### ScenarioWeaver

```python
import asyncio
from venom_core.simulation.scenario_weaver import ScenarioWeaver

async def main(kernel):
    weaver = ScenarioWeaver(kernel=kernel, complexity="medium")
    scenario = await weaver.weave_scenario(
        knowledge_fragment="FastAPI websocket broadcast patterns and retries",
        difficulty="medium",
        libraries=["fastapi", "asyncio"],
    )
    print(scenario.title)
    print(scenario.test_cases)

# asyncio.run(main(kernel))
```

## Public API

### `PersonaFactory`

- `generate_persona(goal, archetype=None, use_llm=False) -> Persona`
- `generate_diverse_personas(goal, count=5, use_llm=False) -> list[Persona]`

### `ScenarioWeaver`

- `weave_scenario(knowledge_fragment, difficulty=None, libraries=None) -> ScenarioSpec`
- `weave_multiple_scenarios(knowledge_fragments, count=5, difficulty=None) -> list[ScenarioSpec]`

## Tests

Run simulation tests:

```bash
pytest tests/test_persona_factory.py -v
pytest tests/test_scenario_weaver.py -v
pytest tests/test_ux_analyst.py -v
```

## Notes for architecture review (task 165)

- This layer is now narrower and easier to maintain.
- Dead references to removed `SimulationDirector` should not be reintroduced.
- Any reactivation of orchestration flow should be done via a dedicated ADR/PR.
