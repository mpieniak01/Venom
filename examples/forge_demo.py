"""
Demo: The Forge - Dynamiczne tworzenie narzędzi

Ten skrypt demonstrowany jak Venom może samodzielnie tworzyć nowe umiejętności.

WYMAGANIA:
- pip install semantic-kernel aiohttp
- Uruchomiony lokalny LLM (Ollama) lub klucz OpenAI API

UŻYCIE:
    python examples/forge_demo.py
"""

import asyncio

from venom_core.agents.toolmaker import ToolmakerAgent
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.execution.skill_manager import SkillManager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


async def demo_create_weather_tool():
    """Demonstracja: Tworzenie narzędzia pogodowego."""
    print("=" * 80)
    print("🔨 THE FORGE DEMO: Weather Tool")
    print("=" * 80)
    print()

    # Zbuduj Kernel
    print("1. Inicjalizacja Semantic Kernel...")
    builder = KernelBuilder()
    kernel = builder.build_kernel()
    print("   ✅ Kernel gotowy")
    print()

    # Inicjalizuj Toolmaker
    print("2. Inicjalizacja Toolmaker Agent...")
    toolmaker = ToolmakerAgent(kernel)
    print("   ✅ Toolmaker gotowy")
    print()

    # Specyfikacja narzędzia
    specification = """Stwórz narzędzie do pobierania informacji o pogodzie.

WYMAGANIA:
- Nazwa klasy: WeatherSkill
- Funkcja: get_current_weather(city: str) -> str
- Używaj Open-Meteo API (https://open-meteo.com) - darmowe, bez klucza API
- Algorytm:
  1. Użyj Geocoding API aby znaleźć koordynaty miasta
  2. Pobierz aktualne dane pogodowe
  3. Zwróć temperaturę i prędkość wiatru
- Kod musi być asynchroniczny (async/await)
- Obsługuj błędy gracefully
"""

    print("3. Toolmaker generuje kod narzędzia...")
    print(f"   Specyfikacja: {specification[:100]}...")
    print()

    # Generuj narzędzie
    success, tool_code = await toolmaker.create_tool(
        specification=specification, tool_name="weather_skill", output_dir=None
    )

    if not success:
        print(f"   ❌ Błąd: {tool_code}")
        return

    print("   ✅ Kod wygenerowany!")
    print()
    print("   Podgląd kodu (pierwsze 500 znaków):")
    print("   " + "-" * 76)
    for line in tool_code[:500].split("\n"):
        print(f"   {line}")
    print("   " + "-" * 76)
    print()

    # Generuj test
    print("4. Toolmaker generuje test jednostkowy...")
    test_success, test_code = await toolmaker.create_test(
        tool_name="weather_skill", tool_code=tool_code, output_dir=None
    )

    if test_success:
        print("   ✅ Test wygenerowany!")
    else:
        print(f"   ⚠️ Nie udało się wygenerować testu: {test_code[:100]}")
    print()

    # Załaduj do Kernela
    print("5. SkillManager ładuje narzędzie do Kernela...")
    skill_manager = SkillManager(kernel)

    reload_success = skill_manager.reload_skill("weather_skill")

    if reload_success:
        print("   ✅ Narzędzie załadowane i gotowe do użycia!")
        print()

        loaded_skills = skill_manager.get_loaded_skills()
        print(f"   📋 Załadowane skills: {loaded_skills}")
        print()

        print("🎉 SUKCES! Weather Tool został stworzony i jest gotowy do użycia!")
        print()
        print("Teraz możesz używać weather_skill w swoich zadaniach:")
        print('   Przykład: "Jaka jest pogoda w Warszawie?"')
        print()
    else:
        print("   ❌ Nie udało się załadować narzędzia")
        print()

    print("=" * 80)


async def demo_create_calculator():
    """Demonstracja: Tworzenie prostego kalkulatora."""
    print("=" * 80)
    print("🔨 THE FORGE DEMO: Calculator Tool")
    print("=" * 80)
    print()

    builder = KernelBuilder()
    kernel = builder.build_kernel()
    toolmaker = ToolmakerAgent(kernel)

    specification = """Stwórz prosty kalkulator matematyczny.

WYMAGANIA:
- Nazwa klasy: CalculatorSkill
- Funkcje:
  - add(a: int, b: int) -> str
  - subtract(a: int, b: int) -> str
  - multiply(a: int, b: int) -> str
  - divide(a: int, b: int) -> str
- Każda funkcja zwraca wynik jako string w formacie "Wynik: X"
- Funkcja divide powinna obsłużyć dzielenie przez zero
"""

    print("Generowanie Calculator Tool...")
    success, tool_code = await toolmaker.create_tool(
        specification=specification, tool_name="calculator_skill", output_dir=None
    )

    if success:
        print("✅ Calculator Tool wygenerowany!")
        print()
        print("Podgląd (pierwsze 400 znaków):")
        print("-" * 80)
        print(tool_code[:400])
        print("-" * 80)
        print()

        # Załaduj
        skill_manager = SkillManager(kernel)
        if skill_manager.reload_skill("calculator_skill"):
            print("✅ Calculator Tool załadowany i gotowy!")
        else:
            print("⚠️ Nie udało się załadować")
    else:
        print(f"❌ Błąd: {tool_code}")

    print("=" * 80)
    print()


async def main():
    """Główna funkcja demo."""
    print()
    print("=" * 80)
    print(" " * 25 + "THE FORGE - DEMO")
    print(" " * 15 + "Dynamiczne Tworzenie Narzędzi")
    print("=" * 80)
    print()
    print("Ten demo pokazuje jak Venom może samodzielnie tworzyć nowe umiejętności.")
    print()

    try:
        # Demo 1: Weather Tool
        await demo_create_weather_tool()

        print("\n" + "=" * 80)
        print("Naciśnij Enter aby przejść do następnego demo...")
        input()

        # Demo 2: Calculator
        await demo_create_calculator()

        print()
        print("=" * 80)
        print("🎉 DEMO ZAKOŃCZONE!")
        print("=" * 80)
        print()
        print("Co dalej?")
        print(
            "- Sprawdź katalog workspace/custom/ aby zobaczyć wygenerowane narzędzia"
        )
        print("- Użyj tych narzędzi w swoich zadaniach przez Venom API")
        print("- Stwórz własne narzędzia modyfikując specyfikację")
        print()

    except KeyboardInterrupt:
        print("\n\n⚠️ Demo przerwane przez użytkownika")
    except Exception as e:
        print(f"\n\n❌ Błąd podczas demo: {e}")
        logger.error(f"Błąd demo: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
