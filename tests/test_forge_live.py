"""Forge scenarios requiring a real model; blocked until host admission exists."""

import tempfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.unsafe_direct_runtime]


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
    - Zainstalowanych zależności Microsoft Agent Framework
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
