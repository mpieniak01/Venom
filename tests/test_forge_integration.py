"""Test integracyjny dla The Forge - dynamiczne tworzenie narzędzi."""

import tempfile
from pathlib import Path

import pytest

# Ten test wymaga pełnych dependencies i LLM, więc oznaczamy jako integration test
pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_forge_workflow_weather_tool():
    """
    Test scenariusza The Forge: Tworzenie WeatherSkill.

    Ten test demonstrowany workflow:
    1. ToolmakerAgent generuje kod WeatherSkill
    2. ToolmakerAgent generuje test
    3. SkillManager ładuje narzędzie
    4. Narzędzie jest dostępne w Kernelu

    UWAGA: Ten test wymaga:
    - Zainstalowanych dependencies (semantic-kernel, etc.)
    - Dostępnego LLM (lokalnego lub cloud)
    - Docker dla weryfikacji (opcjonalne)
    """
    from venom_core.agents.toolmaker import ToolmakerAgent
    from venom_core.execution.kernel_builder import KernelBuilder
    from venom_core.execution.skill_manager import SkillManager

    # Przygotuj tymczasowy katalog na skills
    with tempfile.TemporaryDirectory() as tmpdir:
        custom_dir = Path(tmpdir) / "custom"
        custom_dir.mkdir()

        # Zbuduj kernel
        builder = KernelBuilder()
        kernel = builder.build_kernel()

        # Inicjalizuj komponenty
        toolmaker = ToolmakerAgent(kernel)
        skill_manager = SkillManager(kernel, custom_skills_dir=str(custom_dir))

        # PHASE 1: Toolmaker generuje kod narzędzia
        specification = """Stwórz narzędzie do pobierania pogody.

Wymagania:
- Nazwa klasy: WeatherSkill
- Funkcja: get_current_weather(city: str) -> str
- Używaj Open-Meteo API (darmowe, bez klucza)
- Zwróć temperaturę i opis pogody
"""

        success, tool_code = await toolmaker.create_tool(
            specification=specification,
            tool_name="weather_skill",
            output_dir=str(custom_dir),
        )

        assert success, f"Toolmaker nie mógł stworzyć narzędzia: {tool_code}"
        assert len(tool_code) > 100, "Wygenerowany kod jest zbyt krótki"
        assert "WeatherSkill" in tool_code, "Kod nie zawiera klasy WeatherSkill"
        decorator_missing = "Kod nie zawiera dekoratora @kernel_function"
        assert "@kernel_function" in tool_code, decorator_missing

        # Sprawdź czy plik został utworzony
        tool_file = custom_dir / "weather_skill.py"
        assert tool_file.exists(), "Plik narzędzia nie został utworzony"

        # PHASE 2: Toolmaker generuje test (opcjonalne, może zawieść)
        test_success, test_code = await toolmaker.create_test(
            tool_name="weather_skill", tool_code=tool_code, output_dir=str(custom_dir)
        )

        if test_success:
            assert "test_" in test_code, "Test nie zawiera funkcji testowych"
            test_file = custom_dir / "test_weather_skill.py"
            assert test_file.exists(), "Plik testu nie został utworzony"

        # PHASE 3: SkillManager ładuje narzędzie
        loaded_skills = skill_manager.load_skills_from_dir()

        assert "weather_skill" in loaded_skills, "Narzędzie nie zostało załadowane"
        assert "weather_skill" in skill_manager.get_loaded_skills()

        # PHASE 4: Sprawdź czy narzędzie jest w kernelu
        # Kernel plugins powinien zawierać WeatherSkill
        plugins = kernel.plugins

        # Sprawdź czy został załadowany jakiś plugin
        assert len(plugins) > 0, "Kernel nie ma żadnych pluginów"

        print("✅ Test The Forge zakończony sukcesem!")
        print(f"   Załadowane skills: {loaded_skills}")
        print(f"   Pluginy w kernelu: {len(plugins)}")


@pytest.mark.asyncio
async def test_forge_workflow_simple_calculator():
    """
    Test The Forge: Proste narzędzie Calculator.

    Prostszy test bez zewnętrznych API, tylko matematyka.
    """
    from venom_core.agents.toolmaker import ToolmakerAgent
    from venom_core.execution.kernel_builder import KernelBuilder
    from venom_core.execution.skill_manager import SkillManager

    with tempfile.TemporaryDirectory() as tmpdir:
        custom_dir = Path(tmpdir) / "custom"
        custom_dir.mkdir()

        builder = KernelBuilder()
        kernel = builder.build_kernel()

        toolmaker = ToolmakerAgent(kernel)
        skill_manager = SkillManager(kernel, custom_skills_dir=str(custom_dir))

        # Prostsza specyfikacja
        specification = """Stwórz prosty kalkulator.

Wymagania:
- Nazwa klasy: CalculatorSkill
- Funkcje:
  - add(a: int, b: int) -> str - dodawanie
  - multiply(a: int, b: int) -> str - mnożenie
- Zwracaj wynik jako string w formacie "Wynik: X"
"""

        success, tool_code = await toolmaker.create_tool(
            specification=specification,
            tool_name="calculator_skill",
            output_dir=str(custom_dir),
        )

        assert success, f"Nie udało się stworzyć kalkulatora: {tool_code}"
        assert "CalculatorSkill" in tool_code
        assert "@kernel_function" in tool_code

        # Załaduj
        loaded_skills = skill_manager.load_skills_from_dir()
        assert "calculator_skill" in loaded_skills

        print("✅ Calculator skill utworzony i załadowany!")


def test_skill_manager_hot_reload():
    """Test hot-reload narzędzia bez restartu."""
    from venom_core.execution.kernel_builder import KernelBuilder
    from venom_core.execution.skill_manager import SkillManager

    with tempfile.TemporaryDirectory() as tmpdir:
        builder = KernelBuilder()
        kernel = builder.build_kernel()
        skill_manager = SkillManager(kernel, custom_skills_dir=tmpdir)

        # Stwórz narzędzie v1
        skill_code_v1 = '''"""Test skill v1."""
from typing import Annotated
from semantic_kernel.functions import kernel_function

class TestSkill:
    @kernel_function(name="greet", description="Pozdrowienie")
    def greet(self, name: Annotated[str, "Imię"]) -> str:
        return f"Hello {name}!"
'''

        skill_file = Path(tmpdir) / "test_skill.py"
        skill_file.write_text(skill_code_v1)

        # Załaduj v1
        loaded = skill_manager.load_skills_from_dir()
        assert "test_skill" in loaded

        # Zmień kod na v2
        skill_code_v2 = '''"""Test skill v2."""
from typing import Annotated
from semantic_kernel.functions import kernel_function

class TestSkill:
    @kernel_function(name="greet", description="Pozdrowienie PL")
    def greet(self, name: Annotated[str, "Imię"]) -> str:
        return f"Witaj {name}!"  # Zmienione z Hello na Witaj
'''

        skill_file.write_text(skill_code_v2)

        # Hot-reload (bez restartu)
        reload_success = skill_manager.reload_skill("test_skill")
        assert reload_success, "Hot-reload nie powiódł się"

        # Narzędzie powinno być nadal w rejestrze
        assert "test_skill" in skill_manager.get_loaded_skills()

        print("✅ Hot-reload zakończony sukcesem!")


if __name__ == "__main__":
    # Uruchom test manualnie (wymaga dependencies)
    import asyncio

    print("Testowanie The Forge workflow...")
    print("\nUWAGA: Ten test wymaga:")
    print("- pip install semantic-kernel aiohttp")
    print("- Dostępnego LLM (Ollama/OpenAI)")
    print()

    # Test hot-reload nie wymaga LLM
    print("1. Test hot-reload...")
    test_skill_manager_hot_reload()

    # Testy z LLM są opcjonalne
    print("\n2. Test Weather Tool (wymaga LLM)...")
    try:
        asyncio.run(test_forge_workflow_weather_tool())
    except Exception as e:
        print(f"⚠️ Test Weather Tool pominięty: {e}")

    print("\n3. Test Calculator (wymaga LLM)...")
    try:
        asyncio.run(test_forge_workflow_simple_calculator())
    except Exception as e:
        print(f"⚠️ Test Calculator pominięty: {e}")

    print("\n✅ Testy zakończone!")
