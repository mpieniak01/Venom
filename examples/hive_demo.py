"""
Przykład użycia THE HIVE - Architektura Rozproszonego Przetwarzania.

Ten skrypt demonstruje podstawowe funkcjonalności:
1. Inicjalizacja Message Broker
2. Tworzenie zadań
3. Monitoring statusu
4. Parallel processing (Map-Reduce)
"""

import asyncio
import json
from pathlib import Path

from venom_core.core.ota_manager import OTAManager
from venom_core.infrastructure.message_broker import MessageBroker
from venom_core.utils.logger import get_logger
from venom_core.utils.url_policy import build_http_url

logger = get_logger(__name__)
REDIS_UNAVAILABLE_MESSAGE = "❌ Brak połączenia z Redis - pomijam demo"


async def demo_message_broker():
    """Demo 1: Message Broker - kolejkowanie zadań."""
    print("\n" + "=" * 60)
    print("DEMO 1: Message Broker - Kolejkowanie Zadań")
    print("=" * 60)

    broker = MessageBroker()

    # Próba połączenia z Redis
    print("\n📡 Łączenie z Redis...")
    connected = await broker.connect()

    if not connected:
        print("❌ Brak połączenia z Redis!")
        print("💡 Uruchom Redis: docker run -d -p 6379:6379 redis:alpine")
        print("   Lub użyj StackManager.deploy_default_hive_stack()")
        return None

    print("✅ Połączono z Redis!")

    # Dodawanie zadań
    print("\n📤 Dodawanie zadań do kolejki...")
    task_ids = []

    # High priority task
    task_id = await broker.enqueue_task(
        task_type="user_query",
        payload={"query": "Jak działa Hive?"},
        priority="high_priority",
    )
    task_ids.append(task_id)
    print(f"  ✓ High priority task: {task_id}")

    # Background tasks
    for i in range(3):
        task_id = await broker.enqueue_task(
            task_type="web_scraping",
            payload={"url": f"https://example.com/page{i}"},
            priority="background",
        )
        task_ids.append(task_id)
        print(f"  ✓ Background task {i + 1}: {task_id}")

    # Status kolejek
    print("\n📊 Status kolejek:")
    stats = await broker.get_queue_stats()
    print(f"  High Priority: {stats['high_priority_queue']}")
    print(f"  Background: {stats['background_queue']}")
    print(f"  Pending: {stats['tasks_pending']}")
    print(f"  Connected: {stats['connected']}")

    # Sprawdź status pojedynczego zadania
    if task_ids:
        print(f"\n🔍 Status zadania {task_ids[0]}:")
        task = await broker.get_task_status(task_ids[0])
        if task:
            print(f"  Status: {task.status}")
            print(f"  Type: {task.task_type}")
            print(f"  Priority: {task.priority}")
            print(f"  Created: {task.created_at}")

    await broker.disconnect()
    return broker


async def demo_parallel_processing():
    """Demo 2: Parallel Skill - Map-Reduce."""
    print("\n" + "=" * 60)
    print("DEMO 2: Parallel Processing (Map-Reduce)")
    print("=" * 60)

    broker = MessageBroker()
    connected = await broker.connect()

    if not connected:
        print(REDIS_UNAVAILABLE_MESSAGE)
        return

    from venom_core.execution.skills.parallel_skill import ParallelSkill

    skill = ParallelSkill(broker)

    # Przykład: Przetwarzanie listy URLi
    urls = [
        "https://example.com/article1",
        "https://example.com/article2",
        "https://example.com/article3",
        "https://example.com/article4",
        "https://example.com/article5",
    ]

    print(f"\n📝 Zadanie: Pobierz i stresuść {len(urls)} artykułów")
    print("⚙️  Używam Map-Reduce dla równoległego przetwarzania...")

    # Symulacja map_reduce (w rzeczywistości węzły Spore wykonują zadania)
    result = await skill.map_reduce(
        task_description="Pobierz treść artykułu i stresuść do 2 zdań",
        items=json.dumps(urls),
        priority="high_priority",
        wait_timeout=10,  # Krótki timeout dla demo
    )

    # Parsuj wynik
    try:
        data = json.loads(result)
        print("\n📊 Wyniki:")
        print(f"  Zadania: {data['summary']['total_tasks']}")
        print(f"  Ukończone: {data['summary']['completed']}")
        print(f"  Nieudane: {data['summary']['failed']}")
        print(f"  Pending: {data['summary']['pending']}")
        print(f"  Success rate: {data['summary']['success_rate']}")
    except json.JSONDecodeError:
        print(f"\n📄 Odpowiedź: {result}")

    await broker.disconnect()


async def demo_broadcast():
    """Demo 3: Broadcast Control - komendy do wszystkich węzłów."""
    print("\n" + "=" * 60)
    print("DEMO 3: Broadcast Control")
    print("=" * 60)

    broker = MessageBroker()
    connected = await broker.connect()

    if not connected:
        print(REDIS_UNAVAILABLE_MESSAGE)
        return

    print("\n📢 Wysyłanie broadcast command...")

    # Przykład: STATUS command
    await broker.broadcast_control("STATUS", {"request_id": "demo_123"})
    print("  ✓ STATUS command wysłany do wszystkich węzłów")

    # Przykład: Fake UPDATE_SYSTEM (nie uruchamiamy właściwej aktualizacji)
    print("\n📢 Symulacja UPDATE_SYSTEM broadcast...")
    await broker.broadcast_control(
        "UPDATE_SYSTEM_DEMO",
        {
            "version": "1.2.0",
            "description": "Demo update",
            "package_url": build_http_url("localhost", 8765, "/ota/demo.zip"),
        },
    )
    print("  ✓ UPDATE_SYSTEM_DEMO command wysłany")

    print(
        "\n💡 W rzeczywistości węzły Spore nasłuchują na kanale broadcast"
        " i reagują na komendy"
    )

    await broker.disconnect()


async def demo_ota_package():
    """Demo 4: OTA Manager - tworzenie paczek aktualizacji."""
    print("\n" + "=" * 60)
    print("DEMO 4: OTA Manager - Paczki Aktualizacji")
    print("=" * 60)

    broker = MessageBroker()
    ota = OTAManager(broker)

    print("\n📦 Tworzenie paczki OTA...")

    # Przykład: Pakowanie katalogu docs
    docs_path = Path(__file__).parent.parent / "docs"

    if not docs_path.exists():
        print(f"❌ Katalog {docs_path} nie istnieje")
        return

    package = await ota.create_package(
        version="1.0.0-demo",
        description="Demo OTA package with documentation",
        source_paths=[docs_path],
        include_dependencies=False,
    )

    if package:
        print("✅ Paczka utworzona!")
        print(f"  Wersja: {package.version}")
        print(f"  Opis: {package.description}")
        print(f"  Ścieżka: {package.package_path}")
        print(f"  Checksum: {package.checksum[:16]}...")
        print(f"  Rozmiar: {package.package_path.stat().st_size / 1024:.1f} KB")
    else:
        print("❌ Nie udało się utworzyć paczki")

    # Lista dostępnych paczek
    print("\n📋 Dostępne paczki OTA:")
    packages = ota.list_packages()
    if packages:
        for pkg in packages[:5]:  # Pokaż max 5
            print(
                f"  • {pkg['filename']} ({pkg['version']}) - {pkg['size_bytes']} bytes"
            )
    else:
        print("  (brak paczek)")


async def demo_task_status_monitoring():
    """Demo 5: Monitoring statusu zadań."""
    print("\n" + "=" * 60)
    print("DEMO 5: Monitoring Statusu Zadań")
    print("=" * 60)

    broker = MessageBroker()
    connected = await broker.connect()

    if not connected:
        print(REDIS_UNAVAILABLE_MESSAGE)
        return

    # Utwórz kilka zadań
    print("\n📤 Tworzenie zadań testowych...")
    task_ids = []
    for i in range(5):
        task_id = await broker.enqueue_task(
            task_type="test_task",
            payload={"index": i, "data": f"test data {i}"},
            priority="background",
        )
        task_ids.append(task_id)

    print(f"✅ Utworzono {len(task_ids)} zadań")

    # Symulacja zmian statusu
    print("\n⚙️  Symulacja wykonywania zadań...")
    for i, task_id in enumerate(task_ids):
        if i % 2 == 0:
            # Parzysty - completed
            await broker.update_task_status(
                task_id, status="completed", result=f"Result {i}"
            )
            print(f"  ✓ Task {i}: completed")
        else:
            # Nieparzysty - running
            await broker.update_task_status(task_id, status="running")
            print(f"  ⏳ Task {i}: running")

    # Statystyki
    print("\n📊 Statystyki zadań:")
    stats = await broker.get_queue_stats()
    print(f"  Completed: {stats['tasks_completed']}")
    print(f"  Running: {stats['tasks_running']}")
    print(f"  Pending: {stats['tasks_pending']}")
    print(f"  Failed: {stats['tasks_failed']}")

    await broker.disconnect()


async def main():
    """Główna funkcja demo."""
    print("\n" + "=" * 60)
    print("🐝 THE HIVE - Demo Architektury Rozproszonego Przetwarzania")
    print("=" * 60)

    print("\n📌 Wymagania:")
    print("  • Redis (localhost:6379)")
    print("  • Python 3.10+")
    print("  • Zainstalowane zależności (redis, arq)")

    print("\n🚀 Rozpoczynam demonstracje...\n")

    # Uruchom wszystkie dema
    try:
        await demo_message_broker()
        await demo_parallel_processing()
        await demo_broadcast()
        await demo_ota_package()
        await demo_task_status_monitoring()
    except Exception as e:
        logger.error(f"Błąd podczas demo: {e}", exc_info=True)

    print("\n" + "=" * 60)
    print("✅ Demo zakończone!")
    print("=" * 60)
    print("\n📚 Więcej informacji: docs/THE_HIVE.md")
    print("🔗 GitHub: https://github.com/mpieniak01/Venom")
    print()


if __name__ == "__main__":
    asyncio.run(main())
