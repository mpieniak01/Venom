"""Demo THE_SIMULACRUM - Warstwa Symulacji Użytkowników.

Ten przykład demonstruje:
1. Generowanie person użytkowników
2. Symulację interakcji użytkowników z aplikacją
3. Analizę UX przez UX Analyst
4. Generowanie rekomendacji

Użycie:
    python examples/simulation_demo.py
"""

import asyncio

from venom_core.agents.ux_analyst import UXAnalystAgent
from venom_core.config import SETTINGS
from venom_core.execution.kernel_builder import build_kernel
from venom_core.simulation.director import SimulationDirector
from venom_core.simulation.persona_factory import PersonaFactory
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

logger = get_logger(__name__)


async def demo_persona_factory():
    """Demonstracja generowania person użytkowników."""
    print("\n" + "=" * 70)
    print("DEMO 1: Fabryka Person")
    print("=" * 70)

    # Stwórz fabrykę
    factory = PersonaFactory()

    # Wygeneruj pojedynczą personę
    print("\n📝 Generuję pojedynczą personę...")
    persona = factory.generate_persona(goal="Kupić czerwone buty", archetype="senior")

    print("\n✅ Wygenerowano personę:")
    print(persona.to_json())

    # Wygeneruj zróżnicowane persony
    print("\n📝 Generuję 5 zróżnicowanych person...")
    personas = factory.generate_diverse_personas(
        goal="Zarejestrować konto w aplikacji", count=5
    )

    print(f"\n✅ Wygenerowano {len(personas)} person:")
    for p in personas:
        print(
            f"  - {p.name} ({p.age} lat, tech: {p.tech_literacy.value}, "
            f"cierpliwość: {p.patience})"
        )


async def demo_simple_simulation():
    """Demonstracja prostej symulacji (bez rzeczywistej aplikacji)."""
    print("\n" + "=" * 70)
    print("DEMO 2: Prosta Symulacja (Mock)")
    print("=" * 70)

    print("\n⚠️  UWAGA: Ta demo używa mock URL - dla pełnej symulacji potrzebna jest")
    print("   działająca aplikacja webowa.")

    # Zbuduj kernel
    kernel = await build_kernel()

    # Przygotuj scenariusz
    scenario_desc = "Znaleźć i kliknąć przycisk 'Kontakt'"
    mock_url = "https://example.com"  # Mock URL

    print(f"\n🎬 Scenariusz: {scenario_desc}")
    print(f"   URL: {mock_url}")
    print("   Użytkowników: 3")

    # Wygeneruj persony
    factory = PersonaFactory(kernel=kernel)
    personas = factory.generate_diverse_personas(goal=scenario_desc, count=3)

    print("\n👥 Wygenerowane persony:")
    for p in personas:
        print(
            f"  - {p.name}: {p.age} lat, {p.tech_literacy.value}, "
            f"próg frustracji: {p.frustration_threshold}"
        )

    # UWAGA: Ten przykład nie uruchomi prawdziwej symulacji bez działającej aplikacji
    # Dla pełnej demonstracji, potrzebna jest aplikacja webowa
    print("\n⏭️  Pomijam rzeczywiste uruchomienie symulacji (brak aplikacji)")
    print("   Aby uruchomić pełną symulację, użyj demo_full_simulation()")


async def demo_analysis():
    """Demonstracja analizy UX (wymaga istniejących logów)."""
    print("\n" + "=" * 70)
    print("DEMO 3: Analiza UX")
    print("=" * 70)

    # Zbuduj kernel
    kernel = await build_kernel()

    # Stwórz analityka
    analyst = UXAnalystAgent(kernel=kernel)

    print("\n🔍 Analizuję logi symulacji...")

    # Sprawdź czy są jakieś logi
    logs_dir = SETTINGS.WORKSPACE_ROOT / "simulation_logs"
    if not logs_dir.exists() or not list(logs_dir.glob("session_*.jsonl")):
        print("\n⚠️  Brak logów symulacji do analizy.")
        print("   Uruchom najpierw pełną symulację aby wygenerować logi.")
        return

    # Wykonaj analizę
    analysis = analyst.analyze_sessions()

    if "error" in analysis:
        print(f"\n❌ Błąd analizy: {analysis['error']}")
        return

    print("\n✅ Analiza zakończona:")
    print(f"   Sesji: {analysis['summary']['total_sessions']}")
    print(f"   Sukces: {analysis['summary']['success_rate']}%")
    print(f"   Rage Quits: {analysis['summary']['rage_quits']}")

    if analysis.get("top_problems"):
        print("\n🔥 Najczęstsze problemy:")
        for problem in analysis["top_problems"]:
            print(f"   - {problem['problem']} ({problem['occurrences']}x)")

    # Wygeneruj rekomendacje (jeśli LLM dostępny)
    if SETTINGS.LLM_SERVICE_TYPE != "none":
        print("\n📊 Generuję rekomendacje UX...")
        try:
            recommendations = await analyst.generate_recommendations(analysis)
            print("\n" + "=" * 70)
            print("REKOMENDACJE UX:")
            print("=" * 70)
            print(recommendations)
        except Exception as e:
            print(f"\n⚠️  Nie udało się wygenerować rekomendacji: {e}")


async def demo_full_simulation_with_app():
    """
    Pełna demonstracja z rzeczywistą aplikacją (wymaga uruchomionej aplikacji).

    Ta funkcja pokazuje kompletny workflow:
    1. Wdrożenie stacka aplikacji (opcjonalne)
    2. Spawning użytkowników
    3. Równoległa symulacja
    4. Analiza wyników
    5. Generowanie rekomendacji
    """
    print("\n" + "=" * 70)
    print("DEMO 4: Pełna Symulacja z Aplikacją")
    print("=" * 70)

    # Zbuduj kernel
    kernel = await build_kernel()

    # Stwórz reżysera z włączonym chaosem
    director = SimulationDirector(kernel=kernel, enable_chaos=False)

    # Przykładowa konfiguracja - musisz dostosować do swojej aplikacji
    scenario_config = {
        "stack_name": "test-app",
        "target_url": build_http_url("localhost", 3000),  # Twoja aplikacja
        "scenario_desc": "Zarejestrować nowe konto użytkownika",
        "user_count": 5,
        "max_steps_per_user": 10,
        "deploy_stack": False,  # Ustaw True jeśli chcesz wdrożyć docker-compose
        # "compose_content": "...",  # Zawartość docker-compose.yml
    }

    print("\n🎬 Konfiguracja scenariusza:")
    print(f"   URL: {scenario_config['target_url']}")
    print(f"   Cel: {scenario_config['scenario_desc']}")
    print(f"   Użytkowników: {scenario_config['user_count']}")

    print(
        "\n⚠️  UWAGA: Ta demo wymaga działającej aplikacji pod "
        f"{scenario_config['target_url']}"
    )
    print("   Jeśli aplikacja nie jest dostępna, symulacja się nie powiedzie.")

    # Uruchom symulację
    try:
        print("\n🚀 Uruchamiam symulację...")
        result = await director.run_scenario(**scenario_config)

        print("\n✅ Symulacja zakończona!")
        print(f"   Sukces: {result['success_rate']}%")
        print(
            f"   Użytkownicy sukcesu: {result['successful_users']}/{result['total_users']}"
        )
        print(f"   Rage Quits: {result['rage_quits']}")
        print(f"   Czas trwania: {result['duration_seconds']}s")

        # Wyświetl szczegóły per użytkownik
        if result.get("user_results"):
            print("\n👥 Szczegóły użytkowników:")
            for user_result in result["user_results"]:
                if user_result.get("goal_achieved"):
                    status = "✅"
                elif user_result.get("rage_quit"):
                    status = "😡"
                else:
                    status = "❌"
                print(
                    f"   {status} {user_result['persona_name']}: "
                    f"{user_result['actions_taken']} akcji, "
                    f"frustracja {user_result['frustration_level']}/{user_result['frustration_threshold']}"
                )

        # Analiza UX
        print("\n🔍 Analiza UX...")
        analyst = UXAnalystAgent(kernel=kernel)
        analysis = analyst.analyze_sessions()

        if "error" not in analysis:
            print(f"   Top problemy: {len(analysis.get('top_problems', []))}")
            recommendations = await analyst.generate_recommendations(analysis)
            print("\n" + "=" * 70)
            print("REKOMENDACJE:")
            print("=" * 70)
            print(recommendations)

    except Exception as e:
        print(f"\n❌ Błąd podczas symulacji: {e}")
        logger.exception("Błąd w demo_full_simulation_with_app")

    finally:
        # Czyszczenie
        print("\n🧹 Czyszczenie zasobów...")
        await director.cleanup()


async def main():
    """Główna funkcja demo."""
    print("\n" + "=" * 70)
    print("🧪 VENOM - THE SIMULACRUM DEMO")
    print("   Warstwa Symulacji Użytkowników & Chaos Engineering")
    print("=" * 70)

    # Demo 1: Fabryka Person
    await demo_persona_factory()

    # Demo 2: Prosta symulacja (mock)
    await demo_simple_simulation()

    # Demo 3: Analiza UX (jeśli są logi)
    await demo_analysis()

    # Demo 4: Pełna symulacja (wymaga aplikacji)
    print("\n" + "=" * 70)
    print("💡 PEŁNA SYMULACJA")
    print("=" * 70)
    print("\nAby uruchomić pełną symulację z rzeczywistą aplikacją:")
    print("1. Uruchom swoją aplikację webową (np. na localhost:3000)")
    print("2. Odkomentuj wywołanie demo_full_simulation_with_app() poniżej")
    print("3. Dostosuj parametry w funkcji do swojej aplikacji")
    print("\n# await demo_full_simulation_with_app()")

    print("\n" + "=" * 70)
    print("✅ Demo zakończone!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
