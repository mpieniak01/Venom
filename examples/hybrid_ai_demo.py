"""
Demo: Hybrid AI Engine
Pokazuje jak używać hybrydowego silnika AI w różnych trybach.
"""

import asyncio

from venom_core.config import Settings
from venom_core.execution.model_router import HybridModelRouter, TaskType


async def demo_local_mode():
    """Demo trybu LOCAL - wszystko lokalnie."""
    print("=" * 60)
    print("DEMO 1: Tryb LOCAL (100% prywatności, $0 kosztów)")
    print("=" * 60)

    settings = Settings(AI_MODE="LOCAL")
    router = HybridModelRouter(settings=settings)

    tasks = [
        ("Proste pytanie", TaskType.CHAT, "What is Python?"),
        ("Wrażliwe dane", TaskType.SENSITIVE, "Password: secret123"),
        ("Złożone zadanie", TaskType.CODING_COMPLEX, "Analyze 10 microservices"),
    ]

    for name, task_type, prompt in tasks:
        routing = router.route_task(task_type, prompt)
        print(f"\n{name}:")
        print(f"  Task Type: {task_type.value}")
        print(f"  Target: {routing['target']}")
        print(f"  Provider: {routing['provider']}")
        print(f"  Model: {routing['model_name']}")
        print(f"  Reason: {routing['reason']}")


async def demo_hybrid_mode():
    """Demo trybu HYBRID - inteligentny routing."""
    print("\n" + "=" * 60)
    print("DEMO 2: Tryb HYBRID (Smart routing)")
    print("=" * 60)

    # Symulacja z kluczem API (w prawdziwym użyciu z .env)
    settings = Settings(
        AI_MODE="HYBRID", GOOGLE_API_KEY="demo-key", HYBRID_CLOUD_PROVIDER="google"
    )
    router = HybridModelRouter(settings=settings)

    tasks = [
        ("Chat", TaskType.CHAT, "Hello!"),
        ("Proste kodowanie", TaskType.CODING_SIMPLE, "Write hello world"),
        (
            "Złożone kodowanie",
            TaskType.CODING_COMPLEX,
            "Design microservices architecture",
        ),
        ("Analiza", TaskType.ANALYSIS, "Analyze large dataset"),
        ("Wrażliwe", TaskType.SENSITIVE, "API key: abc123"),
    ]

    for name, task_type, prompt in tasks:
        routing = router.route_task(task_type, prompt)
        print(f"\n{name}:")
        print(f"  Task Type: {task_type.value}")
        print(
            f"  Target: {routing['target']} ← {'🏠 Local' if routing['target'] == 'local' else '☁️ Cloud'}"
        )
        print(f"  Provider: {routing['provider']}")
        print(f"  Model: {routing['model_name']}")


async def demo_cloud_mode():
    """Demo trybu CLOUD - wszystko w chmurze (oprócz wrażliwych)."""
    print("\n" + "=" * 60)
    print("DEMO 3: Tryb CLOUD (Max power)")
    print("=" * 60)

    settings = Settings(
        AI_MODE="CLOUD", GOOGLE_API_KEY="demo-key", HYBRID_CLOUD_PROVIDER="google"
    )
    router = HybridModelRouter(settings=settings)

    tasks = [
        ("Chat", TaskType.CHAT, "Hello!"),
        ("Kodowanie", TaskType.CODING_COMPLEX, "Complex task"),
        ("Wrażliwe", TaskType.SENSITIVE, "Password: secret"),
    ]

    for name, task_type, prompt in tasks:
        routing = router.route_task(task_type, prompt)
        print(f"\n{name}:")
        print(
            f"  Target: {routing['target']} ← {'🏠 Local (Protected!)' if routing['target'] == 'local' else '☁️ Cloud'}"
        )
        print(f"  Provider: {routing['provider']}")
        print(f"  Model: {routing['model_name']}")


async def demo_sensitive_detection():
    """Demo automatycznego wykrywania wrażliwych danych."""
    print("\n" + "=" * 60)
    print("DEMO 4: Automatyczne wykrywanie wrażliwych danych")
    print("=" * 60)

    settings = Settings(
        AI_MODE="CLOUD",  # Nawet w CLOUD, wrażliwe idzie local!
        SENSITIVE_DATA_LOCAL_ONLY=True,
        GOOGLE_API_KEY="demo-key",
    )
    router = HybridModelRouter(settings=settings)

    prompts = [
        ("Normalny tekst", "What is the weather today?"),
        ("Hasło", "My password is secret123"),
        ("API Key", "Here is my API key: abc-def-123"),
        ("Token", "Bearer token xyz789"),
        ("Klucz", "Klucz dostępu: test123"),
    ]

    for name, prompt in prompts:
        is_sensitive = router._is_sensitive_content(prompt)
        routing = router.route_task(TaskType.STANDARD, prompt)

        print(f"\n{name}:")
        print(f"  Prompt: {prompt[:50]}...")
        print(f"  Wykryto wrażliwe: {'✅ TAK' if is_sensitive else '❌ NIE'}")
        print(
            f"  Target: {routing['target']} ← {'🔒 PROTECTED' if routing['target'] == 'local' else '☁️ Cloud'}"
        )


async def demo_fallback():
    """Demo fallback gdy brak dostępu do chmury."""
    print("\n" + "=" * 60)
    print("DEMO 5: Fallback (brak klucza API)")
    print("=" * 60)

    settings = Settings(
        AI_MODE="HYBRID",
        GOOGLE_API_KEY="",  # Brak klucza!
        OPENAI_API_KEY="",
    )
    router = HybridModelRouter(settings=settings)

    routing = router.route_task(TaskType.CODING_COMPLEX, "Design complex architecture")

    print("\nZłożone zadanie BEZ dostępu do chmury:")
    print(f"  Target: {routing['target']} ← Fallback do Local")
    print(f"  Reason: {routing['reason']}")
    print("  ✅ System nadal działa!")


async def main():
    """Uruchom wszystkie demo."""
    print("\n")
    print("🚀 " + "=" * 58 + " 🚀")
    print("   HYBRID AI ENGINE - Demo")
    print("   Local First • Privacy • Zero Cost")
    print("🚀 " + "=" * 58 + " 🚀")

    await demo_local_mode()
    await demo_hybrid_mode()
    await demo_cloud_mode()
    await demo_sensitive_detection()
    await demo_fallback()

    print("\n" + "=" * 60)
    print("✅ Demo zakończone!")
    print("=" * 60)
    print("\nPrzeczytaj więcej: docs/HYBRID_AI_ENGINE.md")


if __name__ == "__main__":
    asyncio.run(main())
