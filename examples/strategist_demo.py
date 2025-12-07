"""Przykład użycia The Strategist - inteligentnego zarządzania modelami."""

import asyncio
import sys
from pathlib import Path

# Dodaj ścieżkę do PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from venom_core.core.model_router import ComplexityScore, ModelRouter
from venom_core.core.prompt_manager import PromptManager
from venom_core.core.token_economist import TokenEconomist
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole


async def example_model_routing():
    """Przykład inteligentnego routingu modeli."""
    print("=" * 60)
    print("PRZYKŁAD 1: Model Router - Inteligentny Routing")
    print("=" * 60)

    router = ModelRouter()

    # Test 1: Proste zadanie
    simple_task = "Napisz funkcję sumującą dwie liczby"
    routing_info = router.get_routing_info(simple_task)
    print(f"\n📝 Zadanie: {simple_task}")
    print(f"   Złożoność: {routing_info['complexity']}")
    print(f"   Wybrany model: {routing_info['selected_service']}")

    # Test 2: Średnio złożone zadanie
    medium_task = "Stwórz REST API z bazą danych PostgreSQL i dodaj testy jednostkowe"
    routing_info = router.get_routing_info(medium_task)
    print(f"\n📝 Zadanie: {medium_task}")
    print(f"   Złożoność: {routing_info['complexity']}")
    print(f"   Wybrany model: {routing_info['selected_service']}")

    # Test 3: Złożone zadanie
    complex_task = "Zaprojektuj architekturę mikroserwisów dla systemu bankowego z wysoką dostępnością"
    routing_info = router.get_routing_info(complex_task)
    print(f"\n📝 Zadanie: {complex_task}")
    print(f"   Złożoność: {routing_info['complexity']}")
    print(f"   Wybrany model: {routing_info['selected_service']}")


async def example_prompt_management():
    """Przykład zarządzania promptami."""
    print("\n" + "=" * 60)
    print("PRZYKŁAD 2: Prompt Manager - Dynamiczne Prompty")
    print("=" * 60)

    manager = PromptManager()

    # Załaduj prompt dla Coder Agent
    try:
        coder_prompt = manager.get_prompt("coder_agent")
        print(f"\n✅ Załadowano prompt dla Coder Agent")
        print(f"   Długość: {len(coder_prompt)} znaków")

        # Pobierz parametry
        params = manager.get_parameters("coder_agent")
        print(f"   Parametry: {params}")
    except FileNotFoundError:
        print("\n⚠️  Plik promptu coder_agent.yaml nie istnieje")

    # Lista dostępnych promptów
    available_prompts = manager.list_prompts()
    print(f"\n📋 Dostępne prompty: {', '.join(available_prompts)}")

    # Status cache
    cache_status = manager.get_cache_status()
    print(f"💾 Prompty w cache: {cache_status['cached_prompts']}")


async def example_token_management():
    """Przykład zarządzania tokenami i kosztami."""
    print("\n" + "=" * 60)
    print("PRZYKŁAD 3: Token Economist - Optymalizacja Kosztów")
    print("=" * 60)

    economist = TokenEconomist()

    # Test 1: Estymacja tokenów
    text = "To jest przykładowy tekst do estymacji liczby tokenów"
    tokens = economist.estimate_tokens(text)
    print(f"\n📊 Tekst: '{text}'")
    print(f"   Estymowana liczba tokenów: {tokens}")

    # Test 2: Kalkulacja kosztów
    usage = {"input_tokens": 1000, "output_tokens": 500}

    cost_gpt35 = economist.calculate_cost(usage, "gpt-3.5-turbo")
    print(f"\n💵 Koszt dla GPT-3.5:")
    print(f"   Input: {cost_gpt35['input_tokens']} tokenów = ${cost_gpt35['input_cost_usd']:.6f}")
    print(f"   Output: {cost_gpt35['output_tokens']} tokenów = ${cost_gpt35['output_cost_usd']:.6f}")
    print(f"   RAZEM: ${cost_gpt35['total_cost_usd']:.6f}")

    cost_gpt4o = economist.calculate_cost(usage, "gpt-4o")
    print(f"\n💵 Koszt dla GPT-4o:")
    print(f"   RAZEM: ${cost_gpt4o['total_cost_usd']:.6f}")

    cost_local = economist.calculate_cost(usage, "local")
    print(f"\n💵 Koszt dla modelu lokalnego:")
    print(f"   RAZEM: ${cost_local['total_cost_usd']:.6f} (darmowy!)")

    # Test 3: Kompresja kontekstu
    history = ChatHistory()
    history.add_message(
        ChatMessageContent(role=AuthorRole.SYSTEM, content="System prompt")
    )

    # Dodaj wiele wiadomości
    for i in range(20):
        history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content=f"User message {i}" * 50)
        )

    print(f"\n🗜️  Kompresja kontekstu:")
    stats_before = economist.get_token_statistics(history)
    print(f"   Przed: {stats_before['total_messages']} wiadomości, {stats_before['total_tokens']} tokenów")

    compressed = economist.compress_context(history, max_tokens=500)
    stats_after = economist.get_token_statistics(compressed)
    print(f"   Po: {stats_after['total_messages']} wiadomości, {stats_after['total_tokens']} tokenów")
    print(f"   Oszczędność: {stats_before['total_tokens'] - stats_after['total_tokens']} tokenów")


async def example_analyst():
    """Przykład audytu wydajności przez Analyst Agent."""
    print("\n" + "=" * 60)
    print("PRZYKŁAD 4: Analyst Agent - Audyt Wydajności")
    print("=" * 60)

    # Import analyst lokalnie aby uniknąć problemów z zależnościami
    try:
        from venom_core.agents.analyst import AnalystAgent, TaskMetrics
        from unittest.mock import Mock

        mock_kernel = Mock()
        analyst = AnalystAgent(kernel=mock_kernel)

        # Symuluj kilka zadań
        print("\n🔄 Symulacja wykonywania zadań...")

        # Zadania lokalne (niski koszt)
        for i in range(5):
            metrics = TaskMetrics(
                task_id=f"local_task_{i}",
                complexity=ComplexityScore.LOW,
                selected_service="local_llm",
                success=True,
                cost_usd=0.0,
                duration_seconds=1.5,
                tokens_used=100,
            )
            analyst.record_task(metrics)

        # Zadania cloud (wyższy koszt)
        for i in range(3):
            metrics = TaskMetrics(
                task_id=f"cloud_task_{i}",
                complexity=ComplexityScore.HIGH,
                selected_service="cloud_high",
                success=True,
                cost_usd=0.05,
                duration_seconds=3.0,
                tokens_used=1000,
            )
            analyst.record_task(metrics)

        # Jedno nieudane zadanie
        metrics = TaskMetrics(
            task_id="failed_task",
            complexity=ComplexityScore.HIGH,
            selected_service="local_llm",
            success=False,
            cost_usd=0.0,
            duration_seconds=5.0,
            tokens_used=500,
        )
        analyst.record_task(metrics)

        # Wygeneruj raport
        report = await analyst.process("Generate report")
        print(report)

    except ImportError as e:
        print(f"\n⚠️  Pominięto przykład Analyst Agent (brak zależności): {e}")


async def example_kernel_builder_integration():
    """Przykład integracji KernelBuilder z nowymi komponentami."""
    print("\n" + "=" * 60)
    print("PRZYKŁAD 5: KernelBuilder - Integracja")
    print("=" * 60)

    try:
        from venom_core.execution.kernel_builder import KernelBuilder

        # Inicjalizacja z routingiem
        builder = KernelBuilder(enable_routing=True)

        print(f"\n✅ KernelBuilder zainicjalizowany")
        print(f"   Model Router: {builder.get_model_router().__class__.__name__}")
        print(f"   Prompt Manager: {builder.get_prompt_manager().__class__.__name__}")
        print(f"   Token Economist: {builder.get_token_economist().__class__.__name__}")

        # Przykład routingu dla różnych zadań
        simple_task = "Napisz Hello World"
        complex_task = "Zaprojektuj system mikroserwisów"

        print(f"\n🎯 Routing dla prostego zadania:")
        simple_routing = builder.get_model_router().get_routing_info(simple_task)
        print(f"   Zadanie: {simple_task}")
        print(f"   Routing: {simple_routing['selected_service']}")

        print(f"\n🎯 Routing dla złożonego zadania:")
        complex_routing = builder.get_model_router().get_routing_info(complex_task)
        print(f"   Zadanie: {complex_task}")
        print(f"   Routing: {complex_routing['selected_service']}")

    except ImportError as e:
        print(f"\n⚠️  Pominięto przykład KernelBuilder (brak zależności): {e}")


async def main():
    """Uruchom wszystkie przykłady."""
    print("\n" + "=" * 60)
    print("THE STRATEGIST - DEMO")
    print("Inteligentne Zarządzanie Modelami i Zasobami")
    print("=" * 60)

    await example_model_routing()
    await example_prompt_management()
    await example_token_management()
    await example_analyst()
    await example_kernel_builder_integration()

    print("\n" + "=" * 60)
    print("✅ DEMO ZAKOŃCZONE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
