"""
Demo: AssistantSkill - Podstawowe umiejętności asystenta.

Ten przykład pokazuje jak używać AssistantSkill do:
1. Pobierania aktualnego czasu
2. Sprawdzania pogody
3. Monitorowania statusu usług

Uruchomienie:
    python examples/demo_assistant_skill.py
"""

import asyncio

from venom_core.execution.skills.assistant_skill import AssistantSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


async def demo_time():
    """Demonstracja pobierania czasu."""
    print("\n" + "=" * 60)
    print("DEMO 1: Pobieranie aktualnego czasu")
    print("=" * 60 + "\n")

    assistant = AssistantSkill()

    # Format krótki
    print("➜ Format krótki:")
    result = await assistant.get_current_time(format_type="short")
    print(result)

    print("\n➜ Format pełny (domyślny):")
    result = await assistant.get_current_time()
    print(result)


async def demo_weather():
    """Demonstracja pobierania pogody."""
    print("\n" + "=" * 60)
    print("DEMO 2: Pobieranie pogody")
    print("=" * 60 + "\n")

    assistant = AssistantSkill()

    # Pogoda dla Warszawy
    print("➜ Pogoda dla Warszawy (jednostki metryczne):")
    result = await assistant.get_weather(location="Warsaw")
    print(result)

    print("\n➜ Pogoda dla Londynu (jednostki imperialne):")
    result = await assistant.get_weather(location="London", units="imperial")
    print(result)

    # Przykład błędu - nieistniejące miasto
    print("\n➜ Nieistniejące miasto (test obsługi błędów):")
    result = await assistant.get_weather(location="XYZ123NonExistent")
    print(result)


async def demo_services():
    """Demonstracja sprawdzania statusu usług."""
    print("\n" + "=" * 60)
    print("DEMO 3: Sprawdzanie statusu usług")
    print("=" * 60 + "\n")

    assistant = AssistantSkill()

    # Podstawowe podsumowanie
    print("➜ Podstawowe podsumowanie:")
    result = await assistant.check_services(detailed=False)
    print(result)

    # Szczegółowe informacje
    print("\n➜ Szczegółowe informacje o usługach:")
    result = await assistant.check_services(detailed=True)
    print(result)


async def main():
    """Główna funkcja demonstracyjna."""
    print("\n" + "█" * 60)
    print("  AssistantSkill - Demo Podstawowych Umiejętności")
    print("█" * 60)

    try:
        # Demo 1: Czas
        await demo_time()

        # Demo 2: Pogoda
        await demo_weather()

        # Demo 3: Status usług
        await demo_services()

        print("\n" + "=" * 60)
        print("Demo zakończone pomyślnie! ✅")
        print("=" * 60 + "\n")

    except Exception as e:
        logger.error(f"Błąd podczas wykonywania demo: {e}")
        print(f"\n❌ Błąd: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
