# Custom Skills Directory

Ten katalog zawiera dynamicznie generowane umiejętności (skills) stworzone przez Venoma.

## Struktura

Każdy skill powinien być plikiem `.py` zawierającym klasę z metodami oznaczonymi `@kernel_function`.

## Przykład

```python
from typing import Annotated
from semantic_kernel.functions import kernel_function

class ExampleSkill:
    @kernel_function(name="example_function", description="Przykładowa funkcja")
    def example_function(self, param: Annotated[str, "Parametr"]) -> str:
        return f"Result: {param}"
```

## Zasady

- Każdy skill musi mieć przynajmniej jedną metodę z `@kernel_function`
- Kod nie może zawierać `eval`, `exec`, `__import__`
- Wszystkie funkcje powinny być bezpieczne i dobrze udokumentowane
