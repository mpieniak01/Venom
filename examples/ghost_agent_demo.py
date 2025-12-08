"""
Przykład użycia Ghost Agent - Visual GUI Automation.

Ten skrypt demonstruje podstawowe możliwości Ghost Agent:
1. Otwieranie aplikacji (Notatnik)
2. Wpisywanie tekstu
3. Interakcja z GUI
"""

import asyncio
import sys
from pathlib import Path

# Dodaj venom_core do ścieżki
sys.path.insert(0, str(Path(__file__).parent.parent))

from venom_core.agents.ghost_agent import GhostAgent
from venom_core.config import SETTINGS
from venom_core.execution.kernel_builder import KernelBuilder


async def demo_notepad():
    """Demo: Otwórz notatnik i napisz tekst."""
    print("=" * 60)
    print("DEMO 1: Otwórz Notatnik i napisz tekst")
    print("=" * 60)

    # Zbuduj kernel
    kernel = KernelBuilder().build()

    # Utwórz Ghost Agent
    ghost = GhostAgent(
        kernel=kernel,
        max_steps=20,
        step_delay=1.0,  # 1 sekunda między krokami
        verification_enabled=False,  # Dla demo wyłączamy weryfikację
    )

    # Wykonaj zadanie
    result = await ghost.process("Otwórz notatnik i napisz 'Hello from Ghost Agent!'")

    print("\n" + result)
    print("\n✅ Demo zakończone")


async def demo_input_skill():
    """Demo: Bezpośrednie użycie InputSkill."""
    print("\n" + "=" * 60)
    print("DEMO 2: Bezpośrednie użycie InputSkill")
    print("=" * 60)

    from venom_core.execution.skills.input_skill import InputSkill

    input_skill = InputSkill(safety_delay=0.5)

    # Pobierz pozycję myszy
    print("\n1. Pobieranie pozycji myszy...")
    position = await input_skill.get_mouse_position()
    print(f"   {position}")

    # Pobierz rozmiar ekranu
    print("\n2. Pobieranie rozmiaru ekranu...")
    width, height = input_skill.get_screen_size()
    print(f"   Rozmiar ekranu: {width}x{height}")

    # Zrób screenshot
    print("\n3. Robienie zrzutu ekranu...")
    screenshot_result = await input_skill.take_screenshot()
    print(f"   {screenshot_result}")

    print("\n✅ Demo zakończone")


async def demo_vision_grounding():
    """Demo: Vision Grounding (wymaga OpenAI API key)."""
    print("\n" + "=" * 60)
    print("DEMO 3: Vision Grounding")
    print("=" * 60)

    if not SETTINGS.OPENAI_API_KEY:
        print("⚠️  UWAGA: Brak OPENAI_API_KEY w konfiguracji")
        print("   Vision Grounding będzie używać fallback (OCR)")
        print("   Ustaw OPENAI_API_KEY w .env aby uzyskać lepsze rezultaty")

    from PIL import ImageGrab

    from venom_core.perception.vision_grounding import VisionGrounding

    vision = VisionGrounding()

    print("\n1. Robienie zrzutu ekranu...")
    screenshot = ImageGrab.grab()
    print(f"   Screenshot: {screenshot.size[0]}x{screenshot.size[1]} pikseli")

    print(
        "\n2. Szukanie elementu 'przycisku Start' (to przykład - może nie znaleźć)..."
    )
    coords = await vision.locate_element(screenshot, description="przycisk Start")

    if coords:
        x, y = coords
        print(f"   ✅ Element znaleziony: ({x}, {y})")
    else:
        print("   ℹ️  Element nie znaleziony (to normalne w demo)")

    print("\n✅ Demo zakończone")


async def main():
    """Główna funkcja demo."""
    print("\n" + "🎭" * 30)
    print("   GHOST AGENT - Visual GUI Automation Demo")
    print("🎭" * 30)

    print("\n⚠️  WAŻNE OSTRZEŻENIA:")
    print("1. Ghost Agent będzie kontrolować mysz i klawiaturę")
    print("2. Przesuń mysz do rogu (0,0) aby NATYCHMIAST przerwać")
    print("3. Upewnij się że nie masz otwartych ważnych aplikacji")
    print("4. Demo najlepiej działa na Windows")

    input("\nNaciśnij Enter aby kontynuować (lub Ctrl+C aby anulować)...")

    try:
        # Demo 1: Notatnik (tylko na Windows/Linux z GUI)
        import platform

        if platform.system() in ["Windows", "Linux"]:
            await demo_notepad()
        else:
            print(f"\n⚠️  Demo 1 pomijane (System: {platform.system()})")

        # Demo 2: InputSkill (działa wszędzie)
        await demo_input_skill()

        # Demo 3: Vision Grounding (wymaga GUI)
        if platform.system() in ["Windows", "Linux"]:
            await demo_vision_grounding()
        else:
            print(f"\n⚠️  Demo 3 pomijane (System: {platform.system()})")

    except KeyboardInterrupt:
        print("\n\n🛑 Demo przerwane przez użytkownika")
    except Exception as e:
        print(f"\n\n❌ Błąd: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 60)
    print("Dziękujemy za wypróbowanie Ghost Agent!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
