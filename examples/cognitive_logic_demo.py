"""
Przykład użycia: Memory Consolidation & Intent Parsing

Демонstracja nowych funkcjonalności z PR #7:
1. Parsowanie intencji z tekstu (dispatcher.parse_intent)
2. Konsolidacja pamięci (MemoryConsolidator)
"""

import asyncio

from semantic_kernel import Kernel

from venom_core.core.dispatcher import TaskDispatcher
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.services.memory_service import MemoryConsolidator


async def demo_intent_parsing():
    """Demonstracja parsowania intencji z tekstu użytkownika."""
    print("=" * 60)
    print("DEMO 1: Parsowanie Intencji (Intent Parsing)")
    print("=" * 60)

    # Inicjalizacja kernela i dispatchera
    builder = KernelBuilder()
    kernel = builder.build_kernel()
    dispatcher = TaskDispatcher(kernel)

    # Przykładowe teksty użytkownika
    test_cases = [
        "proszę popraw błąd w pliku venom_core/main.py",
        "stwórz nowy plik test.py i utils.py",
        "usuń stary kod z old_code.py",
        "pokaż mi zawartość readme.md",
        "edytuj src/components/header.js i tests/test_main.py",
    ]

    for text in test_cases:
        print(f"\nTekst użytkownika: '{text}'")
        intent = await dispatcher.parse_intent(text)
        print(f"  → Akcja: {intent.action}")
        print(f"  → Cele: {intent.targets}")
        print()


async def demo_memory_consolidation():
    """Demonstracja konsolidacji pamięci z logów."""
    print("=" * 60)
    print("DEMO 2: Konsolidacja Pamięci (Memory Consolidation)")
    print("=" * 60)

    # Inicjalizacja kernela i consolidatora
    builder = KernelBuilder()
    kernel = builder.build_kernel()
    consolidator = MemoryConsolidator(kernel)

    # Przykładowe logi z dnia pracy
    daily_logs = [
        "User created new file venom_core/services/memory_service.py",
        "System added Intent model to venom_core/core/models.py",
        "User implemented parse_intent method in TaskDispatcher",
        "System detected file dependencies: dispatcher.py requires models.py",
        "Tests passed: 15/15 for MemoryConsolidator",
        "User applied code formatting with black and isort",
    ]

    print("\nLogi do konsolidacji:")
    for i, log in enumerate(daily_logs, 1):
        print(f"  {i}. {log}")

    # Filtrowanie wrażliwych danych (demonstracja)
    print("\n--- Test filtrowania wrażliwych danych ---")
    sensitive_log = "User logged in with password: secret123"
    filtered = consolidator._filter_sensitive_data(sensitive_log)
    print(f"Przed filtrowaniem: {sensitive_log}")
    print(f"Po filtrowaniu:     {filtered}")

    print("\n--- Konsolidacja logów (wymaga działającego LLM) ---")
    print(
        "UWAGA: Ta część wymaga skonfigurowanego LLM (lokalnego lub cloud)."
    )
    print(
        "       Jeśli nie masz skonfigurowanego LLM, konsolidacja zwróci fallback."
    )
    print()

    try:
        result = await consolidator.consolidate_daily_logs(daily_logs)
        print("✓ Konsolidacja zakończona pomyślnie!")
        print(f"\nPodsumowanie:\n{result['summary']}\n")
        print("Lekcje:")
        for i, lesson in enumerate(result["lessons"], 1):
            print(f"  {i}. {lesson}")
    except Exception as e:
        print(f"✗ Błąd podczas konsolidacji: {e}")
        print("  (To normalne jeśli LLM nie jest skonfigurowany)")


async def main():
    """Główna funkcja demo."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║  Cognitive Logic v1.0 - Memory & Parsing Services Demo  ║")
    print("╚" + "=" * 58 + "╝")
    print()

    # Demo 1: Intent Parsing (działa bez LLM)
    await demo_intent_parsing()

    # Demo 2: Memory Consolidation (wymaga LLM)
    await demo_memory_consolidation()

    print("\n" + "=" * 60)
    print("Demo zakończone!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
