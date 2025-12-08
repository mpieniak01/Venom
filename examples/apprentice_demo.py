"""
Demo: Apprentice Agent - Visual Imitation Learning

Ten skrypt demonstruje możliwości ApprenticeAgent:
- Nagrywanie demonstracji
- Analiza nagranych akcji
- Generowanie workflow
- Odtwarzanie workflow przez GhostAgent
"""

import asyncio
import sys
from pathlib import Path

# Dodaj katalog główny do PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from venom_core.agents.apprentice import ApprenticeAgent
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.memory.workflow_store import WorkflowStore
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


async def demo_apprentice_basic():
    """Demo podstawowych funkcji ApprenticeAgent."""
    logger.info("=== Demo: Apprentice Agent - Podstawy ===\n")

    # Inicjalizuj kernel
    kernel_builder = KernelBuilder()
    kernel = kernel_builder.build_kernel()

    # Utwórz agenta
    apprentice = ApprenticeAgent(kernel)

    logger.info("✅ ApprenticeAgent zainicjalizowany\n")

    # 1. Rozpocznij nagrywanie
    logger.info("📝 Krok 1: Rozpoczęcie nagrywania demonstracji")
    response = await apprentice.process("Rozpocznij nagrywanie nazwany test_demo")
    logger.info(f"Odpowiedź: {response}\n")

    # Symulacja akcji użytkownika (w prawdziwym użyciu, użytkownik wykonuje akcje)
    logger.info("🖱️  Symulacja: Użytkownik wykonuje akcje...")
    await asyncio.sleep(2)

    # Dodaj kilka symulowanych zdarzeń do sesji
    if apprentice.recorder.current_session:
        import time

        from venom_core.perception.recorder import InputEvent

        # Symuluj kliknięcie
        event1 = InputEvent(
            timestamp=time.time(),
            event_type="mouse_click",
            data={"x": 500, "y": 300, "button": "left", "pressed": True},
        )
        apprentice.recorder.current_session.events.append(event1)

        # Symuluj wpisanie tekstu
        for char in "Hello":
            event = InputEvent(
                timestamp=time.time(),
                event_type="key_press",
                data={"key": char},
            )
            apprentice.recorder.current_session.events.append(event)

        # Symuluj Enter
        event_enter = InputEvent(
            timestamp=time.time(),
            event_type="key_press",
            data={"key": "enter"},
        )
        apprentice.recorder.current_session.events.append(event_enter)

        logger.info(
            f"   Dodano {len(apprentice.recorder.current_session.events)} zdarzeń\n"
        )

    # 2. Zatrzymaj nagrywanie
    logger.info("📝 Krok 2: Zatrzymanie nagrywania")
    response = await apprentice.process("Zatrzymaj nagrywanie")
    logger.info(f"Odpowiedź: {response}\n")

    # 3. Analizuj sesję
    logger.info("📝 Krok 3: Analiza demonstracji")
    response = await apprentice.process("Analizuj sesję test_demo")
    logger.info(f"Odpowiedź: {response}\n")

    # 4. Generuj skill
    logger.info("📝 Krok 4: Generowanie workflow")
    response = await apprentice.process("Generuj skill hello_workflow")
    logger.info(f"Odpowiedź: {response}\n")

    # 5. Lista sesji
    sessions = apprentice.recorder.list_sessions()
    logger.info(f"📝 Dostępne sesje: {sessions}\n")

    logger.info("✅ Demo zakończone!")


async def demo_workflow_store():
    """Demo WorkflowStore."""
    logger.info("=== Demo: Workflow Store ===\n")

    # Utwórz WorkflowStore
    workflow_store = WorkflowStore()

    # Lista workflow
    workflows = workflow_store.list_workflows()
    logger.info(f"📝 Liczba workflow: {len(workflows)}")

    for wf in workflows:
        logger.info(
            f"   - {wf['workflow_id']}: {wf['name']} ({wf['steps_count']} kroków)"
        )

    # Jeśli są workflow, załaduj pierwszy
    if workflows:
        wf_id = workflows[0]["workflow_id"]
        logger.info(f"\n📝 Ładowanie workflow: {wf_id}")

        workflow = workflow_store.load_workflow(wf_id)
        if workflow:
            logger.info(f"   Nazwa: {workflow.name}")
            logger.info(f"   Opis: {workflow.description}")
            logger.info("   Kroki:")
            for step in workflow.steps:
                status = "✓" if step.enabled else "✗"
                logger.info(f"      {status} Krok {step.step_id}: {step.description}")

            # Eksportuj do Python
            logger.info("\n📝 Eksport workflow do Python")
            python_path = workflow_store.export_to_python(wf_id)
            logger.info(f"   Plik: {python_path}")

    logger.info("\n✅ Demo zakończone!")


async def interactive_demo():
    """Interaktywne demo - pozwala użytkownikowi testować komendy."""
    logger.info("=== Demo: Apprentice Agent - Tryb Interaktywny ===\n")
    logger.info("Dostępne komendy:")
    logger.info("  - 'rec' / 'start' - rozpocznij nagrywanie")
    logger.info("  - 'stop' - zatrzymaj nagrywanie")
    logger.info("  - 'analyze <session_id>' - analizuj sesję")
    logger.info("  - 'generate <skill_name>' - generuj skill")
    logger.info("  - 'list' - lista sesji")
    logger.info("  - 'workflows' - lista workflow")
    logger.info("  - 'quit' - zakończ demo\n")

    # Inicjalizuj
    kernel_builder = KernelBuilder()
    kernel = kernel_builder.build_kernel()
    apprentice = ApprenticeAgent(kernel)
    workflow_store = WorkflowStore()

    while True:
        try:
            user_input = input("Venom> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "q"]:
                logger.info("👋 Do zobaczenia!")
                break

            if user_input.lower() == "list":
                sessions = apprentice.recorder.list_sessions()
                logger.info(f"Dostępne sesje: {sessions}")
                continue

            if user_input.lower() == "workflows":
                workflows = workflow_store.list_workflows()
                logger.info(f"Dostępne workflow ({len(workflows)}):")
                for wf in workflows:
                    logger.info(f"  - {wf['workflow_id']}: {wf['name']}")
                continue

            # Przetwórz przez ApprenticeAgent
            response = await apprentice.process(user_input)
            logger.info(f"\n{response}\n")

        except KeyboardInterrupt:
            logger.info("\n👋 Przerwano przez użytkownika")
            break
        except Exception as e:
            logger.error(f"❌ Błąd: {e}")


async def main():
    """Główna funkcja demo."""
    logger.info("=" * 70)
    logger.info("VENOM - APPRENTICE AGENT DEMO")
    logger.info("Visual Imitation Learning & Workflow Synthesis")
    logger.info("=" * 70 + "\n")

    # Wybór trybu demo
    logger.info("Wybierz tryb demo:")
    logger.info("1. Demo podstawowe (automatyczne)")
    logger.info("2. Demo Workflow Store")
    logger.info("3. Tryb interaktywny")
    logger.info("0. Wyjście\n")

    try:
        choice = input("Wybór (1-3): ").strip()

        if choice == "1":
            await demo_apprentice_basic()
        elif choice == "2":
            await demo_workflow_store()
        elif choice == "3":
            await interactive_demo()
        elif choice == "0":
            logger.info("👋 Do zobaczenia!")
        else:
            logger.warning("Nieprawidłowy wybór")

    except KeyboardInterrupt:
        logger.info("\n👋 Przerwano")
    except Exception as e:
        logger.error(f"❌ Błąd podczas demo: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
