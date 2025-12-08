"""Demo Strategist Agent - zarządzanie złożonością i planowanie zadań."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from venom_core.agents.strategist import StrategistAgent
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.ops.work_ledger import TaskComplexity, WorkLedger


async def demo_analyze_simple_task():
    """Demo analizy prostego zadania."""
    print("=" * 80)
    print("DEMO 1: Analiza prostego zadania")
    print("=" * 80)

    kernel = KernelBuilder(enable_routing=False).build()
    strategist = StrategistAgent(kernel=kernel)

    task = "Napisz funkcję sumującą dwie liczby"

    result = await strategist.analyze_task(task)
    print(result)


async def demo_analyze_complex_task():
    """Demo analizy złożonego zadania."""
    print("\n" + "=" * 80)
    print("DEMO 2: Analiza złożonego zadania")
    print("=" * 80)

    kernel = KernelBuilder(enable_routing=False).build()
    strategist = StrategistAgent(kernel=kernel)

    task = """
    Stwórz REST API dla systemu e-commerce z następującymi funkcjami:
    - Zarządzanie produktami (CRUD)
    - Koszyk zakupowy z sesją
    - System płatności z integracją Stripe
    - Zarządzanie zamówieniami
    - Panel administracyjny
    - Testy jednostkowe i integracyjne
    - Dokumentacja API
    """

    result = await strategist.analyze_task(task)
    print(result)


async def demo_task_monitoring():
    """Demo monitorowania postępu zadania."""
    print("\n" + "=" * 80)
    print("DEMO 3: Monitorowanie postępu zadania")
    print("=" * 80)

    kernel = KernelBuilder(enable_routing=False).build()
    work_ledger = WorkLedger(storage_path="/tmp/demo_work_ledger.json")
    strategist = StrategistAgent(kernel=kernel, work_ledger=work_ledger)

    # Zaloguj zadanie
    task_id = "demo_task_001"
    work_ledger.log_task(
        task_id=task_id,
        name="Implementacja REST API",
        description="API dla zarządzania użytkownikami",
        estimated_minutes=60,
        complexity=TaskComplexity.MEDIUM,
    )

    # Rozpocznij zadanie
    work_ledger.start_task(task_id)

    # Symulacja postępu z overrun
    print("\n--- Stan początkowy ---")
    print(strategist.monitor_task(task_id))

    # Update 1: 30% po 25 minutach (na dobrej drodze)
    work_ledger.update_progress(task_id, 30, actual_minutes=25)
    print("\n--- Po 25 minutach (30% done) ---")
    print(strategist.monitor_task(task_id))

    # Update 2: 50% po 60 minutach (już przekroczenie!)
    work_ledger.update_progress(task_id, 50, actual_minutes=60)
    print("\n--- Po 60 minutach (50% done) - OVERRUN! ---")
    print(strategist.monitor_task(task_id))

    # Sprawdź czy powinno być wstrzymane
    should_pause = strategist.should_pause_task(task_id)
    print(f"\n⚠️ Czy zadanie powinno być wstrzymane? {should_pause}")


async def demo_api_usage_tracking():
    """Demo śledzenia wykorzystania API."""
    print("\n" + "=" * 80)
    print("DEMO 4: Śledzenie wykorzystania zewnętrznych API")
    print("=" * 80)

    kernel = KernelBuilder(enable_routing=False).build()
    work_ledger = WorkLedger(storage_path="/tmp/demo_api_ledger.json")

    # Niskie limity dla demo
    api_limits = {
        "openai": {"calls": 50, "tokens": 10000},
        "anthropic": {"calls": 30, "tokens": 5000},
    }

    strategist = StrategistAgent(kernel=kernel, work_ledger=work_ledger, api_limits=api_limits)

    # Symuluj zadania używające API
    task1_id = "api_task_001"
    work_ledger.log_task(
        task1_id, "Generowanie opisów produktów", "Opis produktów AI", 30, TaskComplexity.LOW
    )
    work_ledger.start_task(task1_id)

    # Zapisz użycie API
    for i in range(15):
        work_ledger.record_api_usage(task1_id, "openai", tokens=500, ops=1)

    task2_id = "api_task_002"
    work_ledger.log_task(
        task2_id, "Analiza sentymentu recenzji", "Analiza AI", 45, TaskComplexity.MEDIUM
    )
    work_ledger.start_task(task2_id)

    for i in range(20):
        work_ledger.record_api_usage(task2_id, "openai", tokens=300, ops=1)

    # Sprawdź użycie API
    print(strategist.check_api_usage())

    # Sugestie lokalnych fallbacków
    print("\n--- Sugestie lokalnych alternatyw ---")
    print(strategist.suggest_local_fallback("Generowanie obrazów produktów przez DALL-E"))


async def demo_full_report():
    """Demo pełnego raportu z Work Ledger."""
    print("\n" + "=" * 80)
    print("DEMO 5: Raport operacyjny")
    print("=" * 80)

    kernel = KernelBuilder(enable_routing=False).build()
    work_ledger = WorkLedger(storage_path="/tmp/demo_full_ledger.json")
    strategist = StrategistAgent(kernel=kernel, work_ledger=work_ledger)

    # Dodaj kilka zadań dla raportu
    tasks_data = [
        ("task_1", "Konfiguracja CI/CD", 30, TaskComplexity.LOW, 25),
        ("task_2", "Implementacja cache", 60, TaskComplexity.MEDIUM, 55),
        ("task_3", "Refaktoryzacja modułu auth", 120, TaskComplexity.HIGH, 150),
        ("task_4", "Dodanie testów", 45, TaskComplexity.MEDIUM, 40),
    ]

    for task_id, name, estimated, complexity, actual in tasks_data:
        work_ledger.log_task(task_id, name, name, estimated, complexity)
        work_ledger.start_task(task_id)
        work_ledger.update_progress(task_id, 100, actual_minutes=actual, files_touched=5)
        work_ledger.complete_task(task_id, actual)

    # Dodaj jedno zadanie w trakcie
    work_ledger.log_task(
        "task_5", "Integracja z Stripe", "Payment gateway", 90, TaskComplexity.HIGH
    )
    work_ledger.start_task("task_5")
    work_ledger.update_progress("task_5", 40, actual_minutes=50)
    work_ledger.add_risk("task_5", "Zewnętrzne API - możliwe opóźnienia")

    # Wygeneruj raport
    report = strategist.generate_report()
    print(report)


async def demo_epic_task_split():
    """Demo podziału EPIC zadania na mniejsze."""
    print("\n" + "=" * 80)
    print("DEMO 6: Podział EPIC zadania")
    print("=" * 80)

    kernel = KernelBuilder(enable_routing=False).build()
    strategist = StrategistAgent(kernel=kernel)

    epic_task = """
    Zaprojektuj i zaimplementuj kompletny system mikroserwisów dla platformy e-learning:
    - Serwis zarządzania użytkownikami (authentication, authorization, profile)
    - Serwis kursów (tworzenie, edycja, publikacja)
    - Serwis wideo (upload, encoding, streaming)
    - Serwis płatności (integracja Stripe, PayPal)
    - Serwis certyfikatów (generowanie PDF)
    - API Gateway z rate limiting
    - Service Discovery (Consul)
    - Centralne logowanie (ELK Stack)
    - Monitoring (Prometheus + Grafana)
    - Message broker (RabbitMQ)
    - Baza danych per serwis (PostgreSQL, MongoDB)
    - CI/CD pipeline
    - Testy jednostkowe, integracyjne i e2e
    - Dokumentacja architektury i API
    - Deployment na Kubernetes
    """

    result = await strategist.analyze_task(epic_task)
    print(result)


async def main():
    """Uruchom wszystkie dema."""
    print("\n" + "=" * 80)
    print("STRATEGIST AGENT - COMPREHENSIVE DEMO")
    print("Zarządzanie złożonością i planowanie zadań")
    print("=" * 80)

    await demo_analyze_simple_task()
    await demo_analyze_complex_task()
    await demo_task_monitoring()
    await demo_api_usage_tracking()
    await demo_full_report()
    await demo_epic_task_split()

    print("\n" + "=" * 80)
    print("✅ DEMO ZAKOŃCZONE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
