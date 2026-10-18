# Custom Skills Directory

Ten katalog zawiera dynamicznie generowane umiejętności (skills) stworzone przez Venoma.

## Struktura

Każdy skill powinien być plikiem `.py` zawierającym klasę z metodami oznaczonymi `@tool_function`.

## Przykład

```python
from typing import Annotated
from venom_core.execution.agent_contracts import tool_function

class ExampleSkill:
    @tool_function(name="example_function", description="Przykładowa funkcja")
    def example_function(self, param: Annotated[str, "Parametr"]) -> str:
        return f"Result: {param}"
```

## Zasady

- Każdy skill musi mieć przynajmniej jedną metodę z `@tool_function`
- Kod nie może zawierać `eval`, `exec`, `__import__`
- Wszystkie funkcje powinny być bezpieczne i dobrze udokumentowane

Dekorator pochodzi z kontraktu Venoma; rejestr narzędzi przekazuje funkcje do
Microsoft Agent Framework. Nowe umiejętności nie importują Semantic Kernel.
Historyczny lokalny alias `kernel_function` pozostaje obsługiwany przez loader,
lecz pliki importujące zewnętrzny pakiet SK wymagają migracji.
