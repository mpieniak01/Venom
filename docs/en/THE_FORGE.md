# THE FORGE - Dynamic Tool Creation

## Overview

**The Forge** is a system for autonomous creation, testing, and loading of new skills (Skills/Plugins) in real-time. It enables Venom to independently extend its capabilities without requiring application restart.

## Architecture

### Components

#### 1. **SkillManager** (`venom_core/execution/skill_manager.py`)
Manages the lifecycle of dynamic plugins:
- **Dynamic loading**: Imports `.py` files from `custom/` directory
- **Hot-reload**: Reloads modules without application restart (`importlib.reload`)
- **Validation**: Checks code security (AST analysis)
- **Registration**: Adds plugins to Semantic Kernel

```python
from venom_core.execution.skill_manager import SkillManager

# Initialize
skill_manager = SkillManager(kernel)

# Load all skills from custom/
loaded = skill_manager.load_skills_from_dir()

# Hot-reload specific skill
skill_manager.reload_skill("weather_skill")

# List loaded skills
skills = skill_manager.get_loaded_skills()
```

#### 2. **ToolmakerAgent** (`venom_core/agents/toolmaker.py`)
Tool creation expert:
- **Code generation**: Writes professional Semantic Kernel plugins
- **Test generation**: Creates unit tests (pytest)
- **Standard**: Code compliant with PEP8, type hints, docstrings

```python
from venom_core.agents.toolmaker import ToolmakerAgent

toolmaker = ToolmakerAgent(kernel)

# Create tool
success, code = await toolmaker.create_tool(
    specification="Tool for fetching currency rates from NBP API",
    tool_name="currency_skill"
)

# Generate test
success, test = await toolmaker.create_test(
    tool_name="currency_skill",
    tool_code=code
)
```

#### 3. **Forge Workflow** (in `Orchestrator`)
Complete tool creation pipeline:

```
User Request → Architect detects need → Toolmaker creates → Guardian verifies → SkillManager loads
```

**Phases:**
1. **CRAFT**: Toolmaker generates code
2. **TEST**: Toolmaker generates tests
3. **VERIFY**: Guardian checks in Docker Sandbox
4. **LOAD**: SkillManager loads to Kernel

```python
# In Orchestrator
result = await orchestrator.execute_forge_workflow(
    task_id=task_id,
    tool_specification="Fetch weather from Open-Meteo API",
    tool_name="weather_skill"
)
```

## Skill Structure

Each skill is a Python file with a class containing `@kernel_function` methods:

```python
"""Module: weather_skill - weather information retrieval."""

import aiohttp
from typing import Annotated
from semantic_kernel.functions import kernel_function


class WeatherSkill:
    """
    Skill for fetching weather information.

    Uses Open-Meteo API (free, no key required).
    """

    @kernel_function(
        name="get_current_weather",
        description="Fetches current weather for given city"
    )
    async def get_current_weather(
        self,
        city: Annotated[str, "City name (e.g., Warsaw, London)"],
    ) -> str:
        """
        Fetches current weather for city.

        Args:
            city: City name

        Returns:
            Weather description with temperature and conditions
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Geocoding
                geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
                async with session.get(geo_url) as resp:
                    geo_data = await resp.json()

                if not geo_data.get("results"):
                    return f"City not found: {city}"

                lat = geo_data["results"][0]["latitude"]
                lon = geo_data["results"][0]["longitude"]

                # Weather
                weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
                async with session.get(weather_url) as resp:
                    weather_data = await resp.json()

                current = weather_data["current_weather"]
                temp = current["temperature"]
                windspeed = current["windspeed"]

                return f"Weather in {city}: {temp}°C, wind {windspeed} km/h"

        except Exception as e:
            return f"Error fetching weather: {str(e)}"
```

## Security

### AST Validation
SkillManager checks code before loading:

✅ **Allowed:**
- Python standard library
- Popular packages (requests, aiohttp, etc.)
- Classes with `@kernel_function` methods
- Type hints and docstrings

❌ **Forbidden:**
- `eval()`, `exec()`, `compile()`
- Dynamic `__import__()`
- Operations outside workspace (sandboxing FileSkill)
- sys.modules modification without control

### Docker Sandbox
Guardian verifies tools in isolated container before loading into main process.

## Usage

### Via Architect Agent

Architect automatically detects need for new tool:

```json
{
  "steps": [
    {
      "step_number": 1,
      "agent_type": "TOOLMAKER",
      "instruction": "Create tool for fetching currency rates from NBP API",
      "depends_on": null
    },
    {
      "step_number": 2,
      "agent_type": "CODER",
      "instruction": "Use currency_skill to display EUR/PLN rate",
      "depends_on": 1
    }
  ]
}
```

### Via API

```python
# Direct call
task_request = TaskRequest(
    content="Create weather checking tool. If you don't have such a tool, create it."
)

response = await orchestrator.submit_task(task_request)
```

### Via CLI Demo

```bash
python examples/forge_demo.py
```

## Directories

```
venom_core/
├── execution/
│   ├── skill_manager.py           # Dynamic skills manager
│   └── skills/
│       ├── file_skill.py          # Built-in skills
│       ├── git_skill.py
│       └── custom/                # 🔥 Dynamically generated
│           ├── README.md
│           ├── __init__.py
│           ├── weather_skill.py   # Example
│           └── test_weather_skill.py
```

**Note**: `custom/*.py` are in `.gitignore` (except `__init__.py` and `README.md`)

## Usage Examples

### 1. Weather Tool

**User Prompt:**
> "What's the weather in Warsaw? If you don't have the tool, create it."

**Workflow:**
1. Architect detects missing `WeatherSkill`
2. Plans `TOOLMAKER` step
3. Toolmaker generates `weather_skill.py`
4. Guardian verifies in Docker
5. SkillManager loads to Kernel
6. CoderAgent uses `weather_skill.get_current_weather("Warsaw")`

**Result:**
> "Weather in Warsaw: 15°C, wind 12 km/h"

### 2. Currency Tool

**User Prompt:**
> "How much is 100 EUR in PLN?"

**Workflow:**
1. Architect: missing `CurrencySkill` → TOOLMAKER
2. Toolmaker: generates `currency_skill.py` with NBP API
3. Loading
4. Usage: `currency_skill.get_exchange_rate("EUR", "PLN")`

### 3. Email Tool

**User Prompt:**
> "Send email to jan@example.com with meeting reminder"

**Workflow:**
1. Missing `EmailSkill` → TOOLMAKER
2. Skill generation with `smtplib`
3. Security verification (credentials in ENV)
4. Usage

## Hot-Reload

Reloading tool without Venom restart:

```python
# After modifying weather_skill.py
skill_manager.reload_skill("weather_skill")
```

**Use case:**
- Bugfix in existing skill
- Adding new function to skill
- Logic change without interrupting other processes

## Council Integration

In Council mode, Toolmaker can be group member:

```python
# In council_config.py
council_members = [
    architect,
    toolmaker,  # 🔥 New member
    coder,
    critic,
    guardian
]
```

**Discussion:**
- Architect: "We need tool X"
- Toolmaker: "Creating X..."
- Guardian: "Testing X..."
- Coder: "Using X for task"

## Testing

### Unit tests

```bash
pytest tests/test_skill_manager.py -v
```

### Integration tests

```bash
pytest tests/test_forge_integration.py -v -m integration
```

**Required:**
- LLM (Ollama/OpenAI)
- Docker (for verification)

## Limitations

1. **Dependencies**: Skill can only use installed packages
2. **Async**: All I/O operations should be async
3. **Sandbox**: FileSkill restricts operations to `workspace/`
4. **Type hints**: Required for all parameters
5. **Serialization**: Return string, not dict/list (LLM compatibility)

## Roadmap

- [ ] Dashboard UI: Active skills list, reload button
- [ ] Skill marketplace: Sharing skills between Venom instances
- [ ] Auto-update: Automatic skill updates when API changes
- [ ] Versioning: `weather_skill_v1.py`, `weather_skill_v2.py`
- [ ] Dependency management: Auto-install required packages
- [ ] Skill metrics: Usage statistics, performance

## FAQ

**Q: Can I manually create a skill?**
A: Yes! Just create a `.py` file in `custom/` following the template.

**Q: What if skill requires new package?**
A: Currently must install manually. In future: auto-installation.

**Q: Can I commit custom skills to repo?**
A: Yes, remove them from `.gitignore` if you want to version them.

**Q: How to debug skill?**
A: Check logs (`logs/`), use `print()` in skill, or unit tests.

**Q: Hot-reload vs restart?**
A: Hot-reload: Changes code without interrupting processes. Restart: Full Venom restart.

## References

- [Semantic Kernel Plugins](https://learn.microsoft.com/en-us/semantic-kernel/agents/plugins/)
- [Python importlib](https://docs.python.org/3/library/importlib.html)
- [AST Module](https://docs.python.org/3/library/ast.html)
- [Docker SDK Python](https://docker-py.readthedocs.io/)

---

**Status**: ✅ Implemented in Issue #014
**Version**: 1.0
**Date**: 2025-12-07
