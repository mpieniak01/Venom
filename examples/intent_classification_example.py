#!/usr/bin/env python
"""Przykład użycia systemu klasyfikacji intencji."""

import asyncio
import tempfile
from pathlib import Path

from venom_core.core.intent_manager import IntentManager
from venom_core.core.models import TaskRequest
from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager


async def example_direct_classification():
    """Przykład bezpośredniej klasyfikacji intencji."""
    print("=" * 60)
    print("PRZYKŁAD 1: Bezpośrednia klasyfikacja IntentManager")
    print("=" * 60)

    # Uwaga: Ten przykład wymaga działającego lokalnego LLM lub klucza OpenAI
    # W przeciwnym razie użyj testów z mockami

    manager = IntentManager()

    test_inputs = [
        "Napisz funkcję w Pythonie do sortowania listy",
        "Co to jest GraphRAG i jak działa?",
        "Witaj Venom, jak się masz?",
    ]

    for user_input in test_inputs:
        try:
            intent = await manager.classify_intent(user_input)
            print(f"\nWejście: {user_input}")
            print(f"Intencja: {intent}")
        except Exception as e:
            print(f"\nBłąd dla '{user_input}': {e}")
            print("(Upewnij się, że lokalny LLM jest uruchomiony)")


async def example_orchestrator_usage():
    """Przykład użycia z Orchestrator."""
    print("\n" + "=" * 60)
    print("PRZYKŁAD 2: Klasyfikacja przez Orchestrator")
    print("=" * 60)

    # Utwórz tymczasowy plik stanu
    tmp_file = tempfile.NamedTemporaryFile(
        prefix="venom_example_state_",
        suffix=".json",
        delete=False,
    )
    state_file = Path(tmp_file.name)
    tmp_file.close()
    state_manager = StateManager(state_file_path=str(state_file))
    orchestrator = Orchestrator(state_manager)

    # Wyślij zadanie
    request = TaskRequest(content="Zrefaktoruj ten kod Python")
    response = await orchestrator.submit_task(request)

    print(f"\nZadanie utworzone: {response.task_id}")
    print("Status:", response.status)

    # Poczekaj na zakończenie
    print("\nOczekiwanie na klasyfikację...")
    await asyncio.sleep(3)

    # Pobierz wynik
    task = state_manager.get_task(response.task_id)
    if task:
        print(f"\nStatus końcowy: {task.status}")
        print(f"Wynik: {task.result}")
        print("\nLogi:")
        for log in task.logs:
            print(f"  - {log}")

    # Cleanup
    await state_manager.shutdown()
    state_file.unlink(missing_ok=True)


async def main():
    """Główna funkcja przykładu."""
    print("\n🐍 VENOM - Przykład Klasyfikacji Intencji 🧠\n")
    print("Ten przykład pokazuje jak działa system rozpoznawania intencji.")
    print("Wymaga działającego lokalnego LLM (np. Ollama) lub klucza OpenAI.\n")

    try:
        # Przykład 1: Bezpośrednia klasyfikacja
        await example_direct_classification()

        # Przykład 2: Użycie z Orchestrator
        await example_orchestrator_usage()

    except Exception as e:
        print(f"\n❌ Błąd: {e}")
        print("\nUpewnij się, że:")
        print("1. Lokalny serwer LLM jest uruchomiony (np. 'ollama serve')")
        print("2. Model jest pobrany (np. 'ollama pull phi3')")
        print("3. Plik .env jest poprawnie skonfigurowany")


if __name__ == "__main__":
    asyncio.run(main())
