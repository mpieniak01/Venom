"""
Demo: Shadow Agent - Desktop Awareness & Proactive Assistance

Ten skrypt demonstruje działanie Shadow Agent:
1. Monitorowanie schowka
2. Wykrywanie błędów w kodzie
3. Generowanie proaktywnych sugestii
4. Wysyłanie powiadomień systemowych
"""

import asyncio
import time

# Importy z Venom
from venom_core.agents.shadow import ShadowAgent, Suggestion, SuggestionType
from venom_core.perception.desktop_sensor import DesktopSensor, PrivacyFilter
from venom_core.ui.notifier import Notifier
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


async def demo_privacy_filter():
    """Demo 1: Privacy Filter - filtrowanie wrażliwych danych."""
    print("\n" + "=" * 60)
    print("DEMO 1: Privacy Filter")
    print("=" * 60)

    test_cases = [
        ("Mój email to test@example.com", True),
        ("password: mySecretPass123", True),
        ("api_key=abc123xyz456", True),
        ("1234 5678 9012 3456", True),  # Karta kredytowa
        ("To jest zwykły tekst bez tajemnic", False),
        ("def calculate_sum(a, b): return a + b", False),
    ]

    for text, should_be_sensitive in test_cases:
        is_sensitive = PrivacyFilter.is_sensitive(text)
        status = "✅ ZABLOKOWANE" if is_sensitive else "✓ OK"

        print(f"\nTekst: {text[:50]}...")
        print(f"Wrażliwy: {is_sensitive} (oczekiwano: {should_be_sensitive})")
        print(f"Status: {status}")

        # Sprawdź czy wykrycie jest poprawne
        if is_sensitive == should_be_sensitive:
            print("✓ Poprawnie wykryte")
        else:
            print("✗ Błędne wykrycie!")


async def demo_shadow_agent_detection():
    """Demo 2: Shadow Agent - wykrywanie błędów i kodu."""
    print("\n" + "=" * 60)
    print("DEMO 2: Shadow Agent - Wykrywanie błędów")
    print("=" * 60)

    # Mock kernel (w prawdziwej wersji użyj build_kernel)
    from unittest.mock import MagicMock

    from semantic_kernel import Kernel

    mock_kernel = MagicMock(spec=Kernel)

    # Utwórz Shadow Agent
    shadow = ShadowAgent(kernel=mock_kernel, confidence_threshold=0.8)
    await shadow.start()

    # Test Case 1: Błąd Python
    error_text = """
    Traceback (most recent call last):
      File "test.py", line 10, in <module>
        result = divide(10, 0)
      File "test.py", line 5, in divide
        return a / b
    ZeroDivisionError: division by zero
    """

    sensor_data_error = {
        "type": "clipboard",
        "content": error_text,
        "timestamp": time.time(),
    }

    print("\n📋 Schowek: Błąd Python (ZeroDivisionError)")
    suggestion = await shadow.analyze_sensor_data(sensor_data_error)

    if suggestion:
        print(f"✅ Sugestia wygenerowana!")
        print(f"   Typ: {suggestion.suggestion_type}")
        print(f"   Tytuł: {suggestion.title}")
        print(f"   Treść: {suggestion.message}")
        print(f"   Pewność: {suggestion.confidence:.2%}")
    else:
        print("❌ Brak sugestii")

    # Test Case 2: Fragment kodu
    code_text = """
    def calculate_sum(numbers):
        total = 0
        for num in numbers:
            total += num
        return total
    """

    sensor_data_code = {
        "type": "clipboard",
        "content": code_text,
        "timestamp": time.time(),
    }

    print("\n📋 Schowek: Fragment kodu Python")
    suggestion = await shadow.analyze_sensor_data(sensor_data_code)

    if suggestion:
        print(f"✅ Sugestia wygenerowana!")
        print(f"   Typ: {suggestion.suggestion_type}")
        print(f"   Pewność: {suggestion.confidence:.2%}")
    else:
        print("✓ Brak sugestii (confidence poniżej progu)")

    # Test Case 3: Dokumentacja
    window_data = {
        "type": "window",
        "title": "Python Documentation - Tutorial for Beginners",
        "timestamp": time.time(),
    }

    print("\n🪟 Okno: Python Documentation")
    suggestion = await shadow.analyze_sensor_data(window_data)

    if suggestion:
        print(f"✅ Sugestia wygenerowana!")
        print(f"   Typ: {suggestion.suggestion_type}")
        print(f"   Treść: {suggestion.message}")
    else:
        print("✓ Brak sugestii")

    await shadow.stop()


async def demo_desktop_sensor():
    """Demo 3: Desktop Sensor - monitorowanie schowka (symulacja)."""
    print("\n" + "=" * 60)
    print("DEMO 3: Desktop Sensor - Monitorowanie")
    print("=" * 60)

    events_received = []

    async def clipboard_callback(data):
        """Callback dla zmian w schowku."""
        events_received.append(data)
        print(f"\n📋 Zmiana w schowku!")
        print(f"   Długość: {data.get('length')} znaków")
        print(f"   Czas: {data.get('timestamp')}")

    # Utwórz sensor
    sensor = DesktopSensor(clipboard_callback=clipboard_callback, privacy_filter=True)

    print("\n✓ Desktop Sensor zainicjalizowany")
    print("   Privacy Filter: WŁĄCZONY")
    print(f"   System: {sensor.system}")
    print(f"   WSL2: {sensor._is_wsl}")

    # Status
    status = sensor.get_status()
    print(f"\nStatus sensora:")
    for key, value in status.items():
        print(f"   {key}: {value}")

    print("\n💡 W prawdziwej wersji sensor monitoruje schowek w tle")
    print("   i wykrywa zmiany automatycznie.")


async def demo_notifier():
    """Demo 4: Notifier - powiadomienia systemowe (mock)."""
    print("\n" + "=" * 60)
    print("DEMO 4: System Powiadomień")
    print("=" * 60)

    action_triggered = []

    async def action_handler(payload):
        """Handler dla akcji z powiadomień."""
        action_triggered.append(payload)
        print(f"\n🎬 Akcja wykonana: {payload}")

    # Utwórz notifier
    notifier = Notifier(webhook_handler=action_handler)

    print(f"\n✓ Notifier zainicjalizowany")
    print(f"   System: {notifier.system}")
    print(f"   WSL2: {notifier._is_wsl}")

    # Status
    status = notifier.get_status()
    print(f"\nStatus:")
    for key, value in status.items():
        print(f"   {key}: {value}")

    print("\n💡 W prawdziwej wersji notifier wysyła:")
    print("   - Windows: Toast Notifications")
    print("   - Linux: notify-send (libnotify)")
    print("   - WSL2: Bridge do Windows")

    # Przykład akcji
    await action_handler(
        {"type": "error_fix", "error": "ZeroDivisionError", "action": "suggest_fix"}
    )


async def main():
    """Main demo function."""
    print("\n" + "🌟" * 30)
    print("VENOM - Shadow Agent Demo")
    print("Desktop Awareness & Proactive Assistance")
    print("🌟" * 30)

    try:
        # Uruchom wszystkie demo
        await demo_privacy_filter()
        await demo_shadow_agent_detection()
        await demo_desktop_sensor()
        await demo_notifier()

        print("\n" + "=" * 60)
        print("✅ Demo zakończone pomyślnie!")
        print("=" * 60)

        print("\n📝 Jak włączyć Shadow Agent w Venom:")
        print("   1. Ustaw ENABLE_PROACTIVE_MODE=True w .env")
        print("   2. Ustaw ENABLE_DESKTOP_SENSOR=True w .env")
        print("   3. Uruchom serwer: python -m venom_core.main")
        print("   4. Sprawdź status: GET /api/v1/shadow/status")

        print("\n⚙️ Konfiguracja w .env:")
        print("   ENABLE_PROACTIVE_MODE=True")
        print("   ENABLE_DESKTOP_SENSOR=True")
        print("   SHADOW_CONFIDENCE_THRESHOLD=0.8")
        print("   SHADOW_PRIVACY_FILTER=True")

    except Exception as e:
        logger.exception("Błąd podczas demo")
        print(f"\n❌ Błąd: {e}")


if __name__ == "__main__":
    asyncio.run(main())
