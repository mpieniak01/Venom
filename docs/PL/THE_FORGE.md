# THE FORGE - Dynamiczne Tworzenie Narzędzi

## Przegląd

**The Forge** to system autonomicznego tworzenia, testowania i ładowania nowych umiejętności (Skills/Plugins) w czasie rzeczywistym. Umożliwia Venomowi samodzielne rozszerzanie swoich możliwości bez potrzeby restartowania aplikacji.

## Architektura

### Komponenty

#### 1. **SkillManager** (`venom_core/execution/skill_manager.py`)
Zarządza cyklem życia dynamicznych pluginów:
- **Dynamiczne ładowanie**: Importuje pliki `.py` z `custom/` directory
- **Hot-reload**: Przeładowuje moduły bez restartu aplikacji (`importlib.reload`)
- **Walidacja**: Sprawdza bezpieczeństwo kodu (AST analysis)
- **Rejestracja**: Dodaje pluginy do Semantic Kernel

```python
from venom_core.execution.skill_manager import SkillManager

# Inicjalizacja
skill_manager = SkillManager(kernel)

# Załaduj wszystkie skills z custom/
loaded = skill_manager.load_skills_from_dir()

# Hot-reload konkretnego skill
skill_manager.reload_skill("weather_skill")

# Lista załadowanych skills
skills = skill_manager.get_loaded_skills()
```

#### 2. **ToolmakerAgent** (`venom_core/agents/toolmaker.py`)
Ekspert od tworzenia narzędzi:
- **Generowanie kodu**: Pisze profesjonalne pluginy Semantic Kernel
- **Generowanie testów**: Tworzy testy jednostkowe (pytest)
- **Standard**: Kod zgodny z PEP8, type hints, docstringi

```python
from venom_core.agents.toolmaker import ToolmakerAgent

toolmaker = ToolmakerAgent(kernel)

# Stwórz narzędzie
success, code = await toolmaker.create_tool(
    specification="Narzędzie do pobierania kursów walut z NBP API",
    tool_name="currency_skill"
)

# Wygeneruj test
success, test = await toolmaker.create_test(
    tool_name="currency_skill",
    tool_code=code
)
```

#### 3. **Forge Workflow** (w `Orchestrator`)
Kompletny pipeline tworzenia narzędzi:

```
User Request → Architect detects need → Toolmaker creates → Guardian verifies → SkillManager loads
```

**Fazy:**
1. **CRAFT**: Toolmaker generuje kod
2. **TEST**: Toolmaker generuje testy
3. **VERIFY**: Guardian sprawdza w Docker Sandbox
4. **LOAD**: SkillManager ładuje do Kernela

```python
# W Orchestrator
result = await orchestrator.execute_forge_workflow(
    task_id=task_id,
    tool_specification="Pobierz pogodę z Open-Meteo API",
    tool_name="weather_skill"
)
```

## Struktura Skill

Każdy skill to plik Python z klasą zawierającą metody `@kernel_function`:

```python
"""Moduł: weather_skill - pobieranie informacji o pogodzie."""

import aiohttp
from typing import Annotated
from semantic_kernel.functions import kernel_function


class WeatherSkill:
    """
    Skill do pobierania informacji o pogodzie.

    Używa Open-Meteo API (darmowe, bez klucza).
    """

    @kernel_function(
        name="get_current_weather",
        description="Pobiera aktualną pogodę dla podanego miasta"
    )
    async def get_current_weather(
        self,
        city: Annotated[str, "Nazwa miasta (np. Warsaw, London)"],
    ) -> str:
        """
        Pobiera aktualną pogodę dla miasta.

        Args:
            city: Nazwa miasta

        Returns:
            Opis pogody z temperaturą i warunkami
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Geocoding
                geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
                async with session.get(geo_url) as resp:
                    geo_data = await resp.json()

                if not geo_data.get("results"):
                    return f"Nie znaleziono miasta: {city}"

                lat = geo_data["results"][0]["latitude"]
                lon = geo_data["results"][0]["longitude"]

                # Pogoda
                weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
                async with session.get(weather_url) as resp:
                    weather_data = await resp.json()

                current = weather_data["current_weather"]
                temp = current["temperature"]
                windspeed = current["windspeed"]

                return f"Pogoda w {city}: {temp}°C, wiatr {windspeed} km/h"

        except Exception as e:
            return f"Błąd pobierania pogody: {str(e)}"
```

## Bezpieczeństwo

### Walidacja AST
SkillManager sprawdza kod przed załadowaniem:

✅ **Dozwolone:**
- Standard library Python
- Popularne pakiety (requests, aiohttp, etc.)
- Klasy z metodami `@kernel_function`
- Type hints i docstringi

❌ **Zabronione:**
- `eval()`, `exec()`, `compile()`
- `__import__()` dynamiczny
- Operacje poza workspace (sandboxing FileSkill)
- Modyfikacja sys.modules bez kontroli

### Docker Sandbox
Guardian weryfikuje narzędzia w izolowanym kontenerze przed załadowaniem do głównego procesu.

## Użycie

### Przez Architect Agent

Architect automatycznie wykrywa potrzebę nowego narzędzia:

```json
{
  "steps": [
    {
      "step_number": 1,
      "agent_type": "TOOLMAKER",
      "instruction": "Stwórz narzędzie do pobierania kursów walut z NBP API",
      "depends_on": null
    },
    {
      "step_number": 2,
      "agent_type": "CODER",
      "instruction": "Użyj currency_skill aby wyświetlić kurs EUR/PLN",
      "depends_on": 1
    }
  ]
}
```

### Przez API

```python
# Bezpośrednie wywołanie
task_request = TaskRequest(
    content="Stwórz narzędzie do sprawdzania pogody. Jeśli nie masz takiego narzędzia, stwórz je."
)

response = await orchestrator.submit_task(task_request)
```

### Przez CLI Demo

```bash
python examples/forge_demo.py
```

## Katalogi

```
venom_core/
├── execution/
│   ├── skill_manager.py           # Menedżer dynamicznych skills
│   └── skills/
│       ├── file_skill.py          # Built-in skills
│       ├── git_skill.py
│       └── custom/                # 🔥 Dynamicznie generowane
│           ├── README.md
│           ├── __init__.py
│           ├── weather_skill.py   # Przykład
│           └── test_weather_skill.py
```

**Uwaga**: `custom/*.py` są w `.gitignore` (poza `__init__.py` i `README.md`)

## Przykłady Użycia

### 1. Weather Tool

**Prompt użytkownika:**
> "Jaka jest pogoda w Warszawie? Jeśli nie masz narzędzia, stwórz je."

**Workflow:**
1. Architect wykrywa brak `WeatherSkill`
2. Planuje krok `TOOLMAKER`
3. Toolmaker generuje `weather_skill.py`
4. Guardian weryfikuje w Docker
5. SkillManager ładuje do Kernela
6. CoderAgent używa `weather_skill.get_current_weather("Warsaw")`

**Rezultat:**
> "Pogoda w Warszawie: 15°C, wiatr 12 km/h"

### 2. Currency Tool

**Prompt użytkownika:**
> "Ile kosztuje 100 EUR w PLN?"

**Workflow:**
1. Architect: brak `CurrencySkill` → TOOLMAKER
2. Toolmaker: generuje `currency_skill.py` z NBP API
3. Załadowanie
4. Użycie: `currency_skill.get_exchange_rate("EUR", "PLN")`

### 3. Email Tool

**Prompt użytkownika:**
> "Wyślij email do jan@example.com z przypomnieniem o spotkaniu"

**Workflow:**
1. Brak `EmailSkill` → TOOLMAKER
2. Generowanie skill z `smtplib`
3. Weryfikacja bezpieczeństwa (credentials w ENV)
4. Użycie

## Hot-Reload

Przeładowanie narzędzia bez restartu Venoma:

```python
# Po zmodyfikowaniu weather_skill.py
skill_manager.reload_skill("weather_skill")
```

**Use case:**
- Bugfix w istniejącym skill
- Dodanie nowej funkcji do skill
- Zmiana logiki bez przerywania innych procesów

## Integracja z Council

W trybie Council, Toolmaker może być członkiem grupy:

```python
# W council_config.py
council_members = [
    architect,
    toolmaker,  # 🔥 Nowy członek
    coder,
    critic,
    guardian
]
```

**Dyskusja:**
- Architect: "Potrzebujemy narzędzia X"
- Toolmaker: "Tworzę X..."
- Guardian: "Testuję X..."
- Coder: "Używam X do zadania"

## Testowanie

### Testy jednostkowe

```bash
pytest tests/test_skill_manager.py -v
```

### Testy integracyjne

```bash
pytest tests/test_forge_integration.py -v -m integration
```

**Wymagane:**
- LLM (Ollama/OpenAI)
- Docker (dla weryfikacji)

## Ograniczenia

1. **Zależności**: Skill może używać tylko zainstalowanych pakietów
2. **Async**: Wszystkie I/O operations powinny być async
3. **Sandbox**: FileSkill ogranicza operacje do `workspace/`
4. **Type hints**: Wymagane dla wszystkich parametrów
5. **Serializacja**: Zwracaj string, nie dict/list (LLM compatibility)

## Roadmap

- [ ] Dashboard UI: Lista active skills, reload button
- [ ] Skill marketplace: Udostępnianie skills między instancjami Venom
- [ ] Auto-update: Automatyczna aktualizacja skills gdy API się zmienia
- [ ] Wersjonowanie: `weather_skill_v1.py`, `weather_skill_v2.py`
- [ ] Dependency management: Auto-instalacja wymaganych pakietów
- [ ] Skill metrics: Statystyki użycia, performance

## FAQ

**Q: Czy mogę ręcznie stworzyć skill?**
A: Tak! Wystarczy stworzyć plik `.py` w `custom/` zgodnie z templatem.

**Q: Co jeśli skill wymaga nowego pakietu?**
A: Aktualnie musisz zainstalować ręcznie. W przyszłości: auto-instalacja.

**Q: Czy mogę commitować custom skills do repo?**
A: Tak, usuń je z `.gitignore` jeśli chcesz je wersjonować.

**Q: Jak debugować skill?**
A: Sprawdź logi (`logs/`), użyj `print()` w skillsie, lub testy jednostkowe.

**Q: Hot-reload vs restart?**
A: Hot-reload: Zmienia kod bez przerywania procesów. Restart: Pełny restart Venoma.

## Referencje

- [Semantic Kernel Plugins](https://learn.microsoft.com/en-us/semantic-kernel/agents/plugins/)
- [Python importlib](https://docs.python.org/3/library/importlib.html)
- [AST Module](https://docs.python.org/3/library/ast.html)
- [Docker SDK Python](https://docker-py.readthedocs.io/)

---

**Status**: ✅ Zaimplementowane w ramach Issue #014
**Wersja**: 1.0
**Data**: 2025-12-07
