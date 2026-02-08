"""
Demo skrypt pokazujący działanie warstwy pamięci (Memory Layer).

Uruchom:
    python examples/memory_demo.py
"""

import asyncio
from pathlib import Path

from venom_core.agents.gardener import GardenerAgent
from venom_core.memory.graph_store import CodeGraphStore
from venom_core.memory.lessons_store import LessonsStore
from venom_core.utils.url_policy import build_http_url


def demo_graph_store():
    """Demonstracja CodeGraphStore."""
    print("=" * 60)
    print("DEMO 1: CodeGraphStore - Graf Wiedzy o Kodzie")
    print("=" * 60)

    # Utwórz workspace z przykładowym kodem
    workspace = Path("./workspace")
    workspace.mkdir(exist_ok=True)

    # Utwórz przykładowy plik
    sample_file = workspace / "example.py"
    sample_file.write_text("""
import os
from typing import List

class DataProcessor:
    def __init__(self):
        self.data = []

    def process(self, items: List[str]) -> List[str]:
        return [self.transform(item) for item in items]

    def transform(self, item: str) -> str:
        return item.upper()

def main():
    processor = DataProcessor()
    result = processor.process(["hello", "world"])
    print(result)
""")

    # Inicjalizuj GraphStore
    print("\n1. Inicjalizacja CodeGraphStore...")
    graph_store = CodeGraphStore(workspace_root=str(workspace))

    # Skanuj workspace
    print("\n2. Skanowanie workspace...")
    stats = graph_store.scan_workspace(force_rescan=True)
    print(f"   ✓ Zeskanowano {stats['files_scanned']}/{stats['total_files']} plików")
    print(f"   ✓ Znaleziono {stats['nodes']} węzłów i {stats['edges']} krawędzi")

    # Podsumowanie grafu
    print("\n3. Podsumowanie grafu:")
    summary = graph_store.get_graph_summary()
    print(f"   Typy węzłów: {summary['node_types']}")
    print(f"   Typy krawędzi: {summary['edge_types']}")

    # Informacje o pliku
    print("\n4. Informacje o pliku 'example.py':")
    info = graph_store.get_file_info("example.py")
    print(f"   ✓ Klasy: {len(info['classes'])}")
    for cls in info["classes"]:
        print(f"     - {cls['name']}")
    print(f"   ✓ Funkcje: {len(info['functions'])}")
    for func in info["functions"]:
        print(f"     - {func['name']}")

    # Impact analysis
    print("\n5. Analiza wpływu:")
    impact = graph_store.get_impact_analysis("example.py")
    print(f"   {impact['warning']}")

    print("\n✓ Demo CodeGraphStore zakończone\n")


def demo_lessons_store():
    """Demonstracja LessonsStore."""
    print("=" * 60)
    print("DEMO 2: LessonsStore - Magazyn Lekcji")
    print("=" * 60)

    # Inicjalizacja
    print("\n1. Inicjalizacja LessonsStore...")
    lessons_store = LessonsStore()

    # Dodaj kilka przykładowych lekcji
    print("\n2. Dodawanie lekcji...")

    # Lekcja 1: Błąd
    lesson1 = lessons_store.add_lesson(
        situation="Próba użycia biblioteki requests do pobrania danych z API",
        action="Wygenerowano kod z requests.get(url, verify=True)",
        result="BŁĄD: SSL Certificate verification failed",
        feedback="W przyszłości użyj verify=False lub skonfiguruj właściwy certyfikat. Dodaj try-except dla lepszej obsługi błędów.",
        tags=["requests", "ssl", "błąd", "api"],
    )
    print(f"   ✓ Dodano lekcję (błąd): {lesson1.lesson_id[:8]}...")

    # Lekcja 2: Sukces
    lesson2 = lessons_store.add_lesson(
        situation="Parsowanie danych JSON z API",
        action="Użyto json.loads() z obsługą błędów JSONDecodeError",
        result="SUKCES: Dane poprawnie sparsowane",
        feedback="Zawsze używaj try-except przy parsowaniu JSON. Waliduj strukturę danych przed dalszym przetwarzaniem.",
        tags=["json", "sukces", "api", "parsing"],
    )
    print(f"   ✓ Dodano lekcję (sukces): {lesson2.lesson_id[:8]}...")

    # Lekcja 3: Ostrzeżenie
    lesson3 = lessons_store.add_lesson(
        situation="Praca z dużymi zbiorami danych w pandas",
        action="Użyto pd.read_csv() bez określenia dtypes",
        result="OSTRZEŻENIE: Wysokie użycie pamięci",
        feedback="Zawsze określaj dtypes w read_csv() dla lepszej wydajności. Rozważ chunking dla bardzo dużych plików.",
        tags=["pandas", "ostrzeżenie", "performance"],
    )
    print(f"   ✓ Dodano lekcję (ostrzeżenie): {lesson3.lesson_id[:8]}...")

    # Statystyki
    print("\n3. Statystyki magazynu:")
    stats = lessons_store.get_statistics()
    print(f"   Łącznie lekcji: {stats['total_lessons']}")
    print(f"   Unikalne tagi: {stats['unique_tags']}")
    print(f"   Rozkład tagów: {stats['tag_distribution']}")

    # Pobierz wszystkie lekcje
    print("\n4. Lista wszystkich lekcji:")
    all_lessons = lessons_store.get_all_lessons()
    for i, lesson in enumerate(all_lessons, 1):
        status = (
            "🔴" if "błąd" in lesson.tags else "🟢" if "sukces" in lesson.tags else "🟡"
        )
        print(f"   {status} [{i}] {lesson.situation[:50]}...")
        print(f"       💡 {lesson.feedback[:60]}...")

    # Filtrowanie po tagach
    print("\n5. Lekcje z tagiem 'api':")
    api_lessons = lessons_store.get_lessons_by_tags(["api"])
    print(f"   Znaleziono {len(api_lessons)} lekcji")
    for lesson in api_lessons:
        print(f"   - {lesson.situation[:50]}...")

    print("\n✓ Demo LessonsStore zakończone\n")


async def demo_gardener_agent():
    """Demonstracja GardenerAgent."""
    print("=" * 60)
    print("DEMO 3: GardenerAgent - Agent Ogrodnik")
    print("=" * 60)

    workspace = Path("./workspace")
    workspace.mkdir(exist_ok=True)

    # Inicjalizacja
    print("\n1. Inicjalizacja GardenerAgent...")
    graph_store = CodeGraphStore(workspace_root=str(workspace))
    gardener = GardenerAgent(graph_store=graph_store, scan_interval=10)

    # Uruchomienie
    print("\n2. Uruchamianie agenta...")
    await gardener.start()

    # Status
    status = gardener.get_status()
    print(f"   ✓ Status: {'Działa' if status['is_running'] else 'Zatrzymany'}")
    print(f"   ✓ Ostatnie skanowanie: {status['last_scan_time']}")
    print(f"   ✓ Monitorowane pliki: {status['monitored_files']}")

    # Symulacja zmiany - dodaj nowy plik
    print("\n3. Symulacja zmiany - dodawanie nowego pliku...")
    new_file = workspace / "new_module.py"
    new_file.write_text("""
def helper_function(x):
    return x * 2
""")
    print("   ✓ Plik new_module.py utworzony")

    # Poczekaj chwilę na wykrycie zmian
    print("\n4. Oczekiwanie 3 sekundy na wykrycie zmian...")
    await asyncio.sleep(3)

    # Manualne skanowanie
    print("\n5. Manualne skanowanie...")
    scan_stats = gardener.trigger_manual_scan()
    print(f"   ✓ Zeskanowano {scan_stats['files_scanned']} plików")
    print(f"   ✓ Graf zawiera {scan_stats['nodes']} węzłów")

    # Zatrzymanie
    print("\n6. Zatrzymywanie agenta...")
    await gardener.stop()
    print("   ✓ Agent zatrzymany")

    print("\n✓ Demo GardenerAgent zakończone\n")


async def main():
    """Główna funkcja demo."""
    print("\n")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║         VENOM - Memory Layer Demo                         ║")
    print("║   GraphRAG + Episodic Learning + Meta-Uczenie             ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print("\n")

    # Uruchom dema
    try:
        # 1. CodeGraphStore
        demo_graph_store()

        # 2. LessonsStore
        demo_lessons_store()

        # 3. GardenerAgent (asynchroniczny)
        await demo_gardener_agent()

        print("\n" + "=" * 60)
        print("✓ Wszystkie dema zakończone pomyślnie!")
        print("=" * 60)
        print("\nKolej na Ciebie! Sprawdź:")
        print(
            f"  - Dashboard: {build_http_url('localhost', 8000)} (zakładka 🧠 Memory)"
        )
        print(f"  - API: {build_http_url('localhost', 8000, '/api/v1/graph/summary')}")
        print("  - Dokumentacja: docs/MEMORY_LAYER_GUIDE.md")
        print("\n")

    except Exception as e:
        print(f"\n❌ Błąd podczas demo: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    # Uruchom demo
    asyncio.run(main())
