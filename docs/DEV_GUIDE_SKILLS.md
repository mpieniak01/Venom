# Poradnik Tworzenia Skills (Umiejętności) w Venom

Niniejszy dokument opisuje standardy tworzenia nowych umiejętności (Skills) w systemie Venom. Dzięki klasie `BaseSkill` proces jest uproszczony i bezpieczny.

## 1. Szybki Start

Aby stworzyć nową umiejętność, utwórz nowy plik w `venom_core/execution/skills/` (np. `my_custom_skill.py`) i dziedzicz po `BaseSkill`.

```python
from typing import Annotated
from semantic_kernel.functions import kernel_function
from venom_core.execution.skills.base_skill import BaseSkill, async_safe_action

class MyCustomSkill(BaseSkill):
    """
    Krótki opis co robi ten skill.
    """

    @kernel_function(
        name="do_something",
        description="Opis funkcji widoczny dla LLM.",
    )
    @async_safe_action
    async def do_something(
        self,
        param_name: Annotated[str, "Opis parametru dla LLM"],
    ) -> str:
        """
        Docstring funkcji.
        """
        # Twoja logika
        result = perform_logic(param_name)

        # Logowanie (masz dostęp do self.logger)
        self.logger.info(f"Wykonano akcję: {result}")

        return f"✅ Sukces: {result}"
```

## 2. Kluczowe Komponenty

### Klasa `BaseSkill`
Zapewnia:
- **Logger (`self.logger`)**: Automatycznie skonfigurowany logger.
- **Workspace (`self.workspace_root`)**: Bezpieczna ścieżka do katalogu roboczego.
- **Metody pomocnicze**: np. `validate_path(path)` dla bezpieczeństwa plików.

### Dekoratory
Używaj dekoratorów `safe_action` (dla metod synchronicznych) lub `async_safe_action` (dla asynchronicznych), aby:
- Automatycznie łapać wyjątki.
- Logować błędy.
- Zwracać sformatowany komunikat błędu ("❌ ...") zamiast przerywać działanie agenta.

**Przykład:**
```python
@async_safe_action
async def risky_method(self):
    raise ValueError("Ups!")
    # Zwróci: "❌ Wystąpił błąd: Ups!"
```

### Typowanie
Używaj `Annotated[Typ, "Opis"]` dla wszystkich argumentów funkcji `@kernel_function`. Te opisy są kluczowe dla LLM, aby wiedział jak używać narzędzia.

## 3. Bezpieczeństwo

Jeśli Twój skill operuje na plikach, **ZAWSZE** używaj `self.validate_path(path)`.
Metoda ta upewnia się, że ścieżka nie wykracza poza dozwolony `workspace_root` (zapobiega Path Traversal).

```python
def read(self, path: str):
    safe_path = self.validate_path(path)
    # Teraz safe_path jest bezpieczna do użycia
    with open(safe_path, 'r') as f: ...
```

## 4. Testowanie

Każdy nowy skill musi posiadać testy jednostkowe w `tests/`.
- Testuj sukces ("✅").
- Testuj błędy (oczekuj zwrotu stringa z błędem "❌", a nie rzucenia wyjątku).
- Używaj `pytest.mark.asyncio` dla metod asynchronicznych.

***

## 5. Import Narzędzi MCP (Model Context Protocol)

Venom obsługuje standard **MCP (Model Context Protocol)**, co pozwala na importowanie narzędzi bezpośrednio z repozytoriów Git bez konieczności pisania własnego wrapper'a.

### Jak to działa?
1.  **Agenci używają skilla `McpManagerSkill`**.
2.  System klonuje repozytorium do `venom_core/skills/mcp/_repos`.
3.  Tworzone jest izolowane środowisko `venv` dla narzędzia.
4.  Generator tworzy plik `.py` w `custom/`, który działa jak "Proxy" do serwera MCP.

### Przykład Użycia (przez Agenta)
```python
# Agent prosi o pobranie narzędzia
await mcp_manager.import_mcp_tool_from_git(
    repo_url="https://github.com/modelcontextprotocol/servers",
    tool_name="sqlite",
    server_entrypoint="python src/sqlite/server.py" # Ścieżka względna w repo
)
```

Po wykonaniu tej operacji, w systemie pojawi się nowy skill (np. `SqliteMcpSkill`), który udostępnia funkcje serwera MCP (np. `query`, `list_tables`) jako natywne `@kernel_function`.

### Struktura MCP w Venomie
*   `venom_core/skills/mcp/` - Logika managera i generatora.
*   `venom_core/skills/mcp/_repos/` - Sklonowane repozytoria (nie edytuj ręcznie).
*   `venom_core/skills/custom/mcp_*.py` - Wygenerowane wrappery (można podglądać, nie edytować).
