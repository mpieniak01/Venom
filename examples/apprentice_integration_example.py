"""
Integration Example: Apprentice + Ghost Agent

Pokazuje pełny cykl:
1. Nagranie demonstracji przez użytkownika
2. Analiza i wygenerowanie skill
3. Wykonanie wygenerowanego skill przez GhostAgent
"""

import asyncio
from pathlib import Path

from venom_core.agents.apprentice import ApprenticeAgent
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.memory.workflow_store import WorkflowStore
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


async def example_full_cycle():
    """
    Przykład pełnego cyklu uczenia i wykonania.

    UWAGA: Ten przykład wymaga rzeczywistego GUI do pełnego działania.
    W środowisku headless można przetestować tylko część analityczną.
    """
    logger.info("=== Przykład: Pełny Cykl Uczenia przez Obserwację ===\n")

    # Inicjalizacja
    kernel_builder = KernelBuilder()
    kernel = kernel_builder.build_kernel()

    apprentice = ApprenticeAgent(kernel)
    # ghost = GhostAgent(kernel)  # Zarezerwowane na przyszłość
    # workflow_store = WorkflowStore()  # Zarezerwowane na przyszłość

    # FAZA 1: Nagrywanie Demonstracji
    logger.info("📝 FAZA 1: Nagrywanie Demonstracji")
    logger.info("-" * 50)

    # W prawdziwym scenariuszu:
    # 1. Użytkownik mówi: "Venom, patrz jak loguję się do banku"
    # 2. System rozpoczyna nagrywanie
    # 3. Użytkownik wykonuje akcje
    # 4. Użytkownik mówi: "Zrobione"
    # 5. System zatrzymuje nagrywanie

    logger.info("Symulacja: Użytkownik rozpoczyna nagrywanie...")
    response = await apprentice.process("Rozpocznij nagrywanie nazwany bank_login")
    logger.info(response)

    # Symulacja akcji użytkownika
    logger.info("\n🖱️  Symulacja akcji użytkownika...")
    logger.info("   1. Kliknięcie w pole 'Username'")
    logger.info("   2. Wpisanie nazwy użytkownika")
    logger.info("   3. Kliknięcie w pole 'Password'")
    logger.info("   4. Wpisanie hasła")
    logger.info("   5. Kliknięcie przycisku 'Login'")

    # W tym miejscu w prawdziwym systemie użytkownik wykonuje akcje
    # a system nagrywa je automatycznie
    await asyncio.sleep(1)

    logger.info("\nUżytkownik: 'Zrobione'")
    response = await apprentice.process("Zatrzymaj nagrywanie")
    logger.info(response)

    # FAZA 2: Analiza i Generowanie Workflow
    logger.info("\n\n📝 FAZA 2: Analiza i Generowanie Workflow")
    logger.info("-" * 50)

    logger.info("Venom analizuje demonstrację...")
    response = await apprentice.process("Analizuj sesję bank_login")
    logger.info(response)

    logger.info("\n\nVenom generuje skill...")
    response = await apprentice.process("Generuj skill bank_login_skill")
    logger.info(response)

    # FAZA 3: Weryfikacja Wygenerowanego Kodu
    logger.info("\n\n📝 FAZA 3: Weryfikacja Wygenerowanego Kodu")
    logger.info("-" * 50)

    skill_file = Path(apprentice.custom_skills_dir) / "bank_login_skill.py"
    if skill_file.exists():
        logger.info(f"✅ Skill wygenerowany: {skill_file}")
        logger.info("\nPodgląd kodu:")
        logger.info("=" * 50)

        code = skill_file.read_text()
        # Pokaż tylko pierwsze 20 linii
        lines = code.split("\n")[:20]
        for line in lines:
            logger.info(line)

        logger.info("...")
        logger.info("=" * 50)

    # FAZA 4: Wykonanie przez GhostAgent (w prawdziwym środowisku)
    logger.info("\n\n📝 FAZA 4: Wykonanie przez GhostAgent")
    logger.info("-" * 50)

    logger.info("W prawdziwym scenariuszu:")
    logger.info("  Użytkownik: 'Venom, zaloguj się do banku'")
    logger.info("  Venom: 'Wykonuję workflow bank_login_skill...'")
    logger.info("  GhostAgent: [Wykonuje wygenerowany kod]")
    logger.info("  Venom: 'Zalogowano pomyślnie'")

    # W środowisku z GUI można by wykonać:
    # result = await ghost.process("Wykonaj skill bank_login_skill")

    logger.info("\n✅ Przykład zakończony!")
    logger.info("\nPodsumowanie:")
    logger.info("1. Użytkownik zademonstrował workflow (login do banku)")
    logger.info("2. System przeanalizował demonstrację")
    logger.info("3. System wygenerował skrypt Python")
    logger.info("4. Skrypt gotowy do wykonania przez GhostAgent")


def example_workflow_editing():
    """
    Przykład edycji wygenerowanego workflow.

    Po wygenerowaniu, użytkownik może chcieć zmodyfikować workflow
    (np. dodać krok, zmienić opis, wyłączyć krok).
    """
    logger.info("=== Przykład: Edycja Workflow ===\n")

    workflow_store = WorkflowStore()

    # Załóżmy że mamy już workflow
    workflows = workflow_store.list_workflows()

    if not workflows:
        logger.info(
            "Brak workflow do edycji. Najpierw wygeneruj workflow używając apprentice_demo.py"
        )
        return

    # Weź pierwszy workflow
    wf_id = workflows[0]["workflow_id"]
    logger.info(f"Edycja workflow: {wf_id}")

    workflow = workflow_store.load_workflow(wf_id)
    if not workflow:
        logger.error("Błąd ładowania workflow")
        return

    logger.info(f"\nOryginalny workflow ({len(workflow.steps)} kroków):")
    for step in workflow.steps:
        status = "✓" if step.enabled else "✗"
        logger.info(f"  {status} Krok {step.step_id}: {step.description}")

    # Przykład 1: Aktualizacja kroku (zmiana opisu)
    if workflow.steps:
        logger.info("\n📝 Aktualizacja kroku 1...")
        workflow_store.update_step(
            wf_id,
            1,
            {"description": "ZAKTUALIZOWANY: " + workflow.steps[0].description},
        )

    # Przykład 2: Dodanie nowego kroku (wait)
    from venom_core.memory.workflow_store import WorkflowStep

    logger.info("📝 Dodawanie nowego kroku (wait 2s)...")
    new_step = WorkflowStep(
        step_id=0,  # Zostanie nadpisane
        action_type="wait",
        description="Czekaj 2 sekundy",
        params={"duration": 2.0},
    )
    workflow_store.add_step(wf_id, new_step)

    # Przykład 3: Wyłączenie kroku
    if len(workflow.steps) > 1:
        logger.info("📝 Wyłączanie kroku 2...")
        workflow_store.update_step(wf_id, 2, {"enabled": False})

    # Załaduj ponownie i pokaż
    workflow = workflow_store.load_workflow(wf_id)
    logger.info(f"\nZmodyfikowany workflow ({len(workflow.steps)} kroków):")
    for step in workflow.steps:
        status = "✓" if step.enabled else "✗"
        logger.info(f"  {status} Krok {step.step_id}: {step.description}")

    # Eksportuj do Python
    logger.info("\n📝 Eksport zmodyfikowanego workflow do Python...")
    python_path = workflow_store.export_to_python(wf_id)
    logger.info(f"✅ Wyeksportowano do: {python_path}")

    logger.info("\n✅ Przykład zakończony!")


def example_parametrization():
    """
    Przykład parametryzacji workflow.

    Pokazuje jak system rozpoznaje zmienne i umożliwia parametryzację.
    """
    logger.info("=== Przykład: Parametryzacja Workflow ===\n")

    logger.info("W tym przykładzie pokazujemy jak system rozpoznaje:")
    logger.info("1. Stałe wartości (np. URL)")
    logger.info("2. Zmienne wartości (np. dane użytkownika)")
    logger.info("3. Wrażliwe dane (np. hasła)\n")

    logger.info("Scenariusz: Login do systemu")
    logger.info("-" * 50)

    logger.info("\nDemonstracja użytkownika:")
    logger.info("  1. Otwórz stronę: https://example.com/login (STAŁA)")
    logger.info("  2. Wpisz email: john@example.com (ZMIENNA)")
    logger.info("  3. Wpisz hasło: ******* (WRAŻLIWE)")
    logger.info("  4. Kliknij 'Login' (AKCJA)")

    logger.info("\nSystem analizuje i pyta:")
    logger.info("  Venom: 'Zauważyłem że wpisałeś \"john@example.com\".'")
    logger.info("         'Czy to ma być parametr (zmienna) czy stała wartość?'")
    logger.info("  Użytkownik: 'Parametr'")
    logger.info("  Venom: 'OK, utworzę parametr \"email\"'")

    logger.info("\nWygenerowany kod:")
    logger.info("=" * 50)
    logger.info("""
async def login_workflow(ghost_agent: GhostAgent, **kwargs):
    # Parametry
    email = kwargs.get("email", "john@example.com")  # Domyślna wartość
    password = kwargs.get("password", "")  # Wymagany parametr

    # Stała wartość
    url = "https://example.com/login"

    # Workflow
    await ghost_agent.vision_click(description="URL bar")
    await ghost_agent.input_skill.keyboard_type(text=url)
    await ghost_agent.input_skill.keyboard_hotkey(["enter"])

    await ghost_agent.vision_click(description="email field")
    await ghost_agent.input_skill.keyboard_type(text=email)

    await ghost_agent.vision_click(description="password field")
    await ghost_agent.input_skill.keyboard_type(text=password)

    await ghost_agent.vision_click(description="login button")
""")
    logger.info("=" * 50)

    logger.info("\nUżycie:")
    logger.info("  # Z domyślnymi wartościami")
    logger.info("  await login_workflow(ghost, password='secret123')")
    logger.info("")
    logger.info("  # Z własnymi wartościami")
    logger.info(
        "  await login_workflow(ghost, email='alice@example.com', password='pass456')"
    )

    logger.info("\n✅ Przykład zakończony!")


async def main():
    """Główna funkcja przykładów integracji."""
    logger.info("=" * 70)
    logger.info("VENOM - APPRENTICE + GHOST INTEGRATION EXAMPLES")
    logger.info("=" * 70 + "\n")

    logger.info("Wybierz przykład:")
    logger.info("1. Pełny cykl (nagrywanie → analiza → generowanie → wykonanie)")
    logger.info("2. Edycja workflow")
    logger.info("3. Parametryzacja workflow")
    logger.info("0. Wyjście\n")

    try:
        choice = (await asyncio.to_thread(input, "Wybór (1-3): ")).strip()

        if choice == "1":
            await example_full_cycle()
        elif choice == "2":
            example_workflow_editing()
        elif choice == "3":
            example_parametrization()
        elif choice == "0":
            logger.info("👋 Do zobaczenia!")
        else:
            logger.warning("Nieprawidłowy wybór")

    except KeyboardInterrupt:
        logger.info("\n👋 Przerwano")
    except Exception as e:
        logger.error(f"❌ Błąd: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
