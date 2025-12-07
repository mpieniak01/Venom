"""
Przykład użycia THE_ACADEMY - Knowledge Distillation & Autonomous Fine-Tuning.

Ten skrypt demonstruje:
1. Generowanie datasetu z historii (LessonsStore, Git, Task History)
2. Uruchomienie treningu LoRA w kontenerze GPU
3. Ewaluację i promocję nowego modelu
4. Zarządzanie wersjami modeli

Wymagania:
- Docker zainstalowany i działający
- Opcjonalnie: nvidia-container-toolkit dla treningu GPU
- Zebrane dane w LessonsStore (minimum 50 lekcji)
"""

import asyncio
from pathlib import Path

from venom_core.agents.professor import Professor
from venom_core.core.model_manager import ModelManager
from venom_core.execution.kernel_builder import KernelBuilder
from venom_core.infrastructure.gpu_habitat import GPUHabitat
from venom_core.learning.dataset_curator import DatasetCurator
from venom_core.memory.lessons_store import LessonsStore
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


async def main():
    """Główna funkcja demonstracyjna."""

    print("=" * 60)
    print("THE ACADEMY - Knowledge Distillation Demo")
    print("=" * 60)
    print()

    # Krok 1: Inicjalizacja komponentów
    print("[1/6] Inicjalizacja komponentów...")

    # LessonsStore
    lessons_store = LessonsStore()

    # Dodaj przykładowe lekcje (jeśli baza jest pusta)
    if lessons_store.get_statistics()["total_lessons"] < 50:
        print("   Dodaję przykładowe lekcje do demonstracji...")
        for i in range(60):
            lessons_store.add_lesson(
                situation=f"Użytkownik poprosił o napisanie funkcji Fibonacci (iteracja {i})",
                action="Utworzyłem funkcję iteracyjną z pamięcią podręczną",
                result="✅ Sukces - kod działa poprawnie i jest wydajny",
                feedback="Iteracyjne podejście jest lepsze dla dużych n od rekurencji",
                tags=["python", "algorytmy", "optimization"],
            )

    # DatasetCurator
    curator = DatasetCurator(lessons_store=lessons_store)

    # GPUHabitat (z fallbackiem na CPU jeśli brak GPU)
    try:
        gpu_habitat = GPUHabitat(enable_gpu=True)
    except Exception as e:
        logger.warning(f"Nie można zainicjalizować GPU: {e}")
        print("   ⚠️ GPU niedostępne, używam trybu CPU")
        gpu_habitat = GPUHabitat(enable_gpu=False)

    # KernelBuilder i Professor
    kernel_builder = KernelBuilder()
    kernel = kernel_builder.build_kernel()
    professor = Professor(
        kernel=kernel,
        dataset_curator=curator,
        gpu_habitat=gpu_habitat,
        lessons_store=lessons_store,
    )

    # ModelManager
    model_manager = ModelManager()

    print("   ✅ Komponenty zainicjalizowane")
    print()

    # Krok 2: Sprawdzenie kryteriów treningu
    print("[2/6] Sprawdzanie kryteriów treningu...")
    decision = professor.should_start_training()
    print(f"   Decyzja: {'✅ TAK' if decision['should_train'] else '❌ NIE'}")
    print(f"   Powód: {decision['reason']}")
    print()

    if not decision["should_train"]:
        print("⚠️ Nie spełniono kryteriów treningu. Kończę demo.")
        return

    # Krok 3: Generowanie datasetu
    print("[3/6] Generowanie datasetu treningowego...")
    result = await professor.process("przygotuj materiały do nauki")
    print(result)
    print()

    # Sprawdź czy dataset został utworzony
    training_dir = Path("./data/training")
    if not training_dir.exists() or not list(training_dir.glob("dataset_*.jsonl")):
        print("❌ Nie udało się utworzyć datasetu. Kończę demo.")
        return

    # Krok 4: Uruchomienie treningu (DEMO - nie uruchamia prawdziwego treningu)
    print("[4/6] Uruchomienie treningu...")
    print("   ⚠️ W trybie DEMO pomijam prawdziwy trening (wymaga GPU i czasu)")
    print("   W produkcji użyj: await professor.process('rozpocznij trening')")
    print()

    # Symuluj zarejestrowanie nowej wersji modelu
    print("   Symulacja: Rejestracja nowej wersji modelu...")
    model_manager.register_version(
        version_id="v1.0",
        base_model="phi3:latest",
        adapter_path=None,
        performance_metrics={"accuracy": 0.85, "loss": 0.3},
    )

    model_manager.register_version(
        version_id="v1.1",
        base_model="phi3:latest",
        adapter_path="./data/models/training_0/adapter",
        performance_metrics={"accuracy": 0.92, "loss": 0.18},
    )

    print("   ✅ Zarejestrowano wersje: v1.0, v1.1")
    print()

    # Krok 5: Ewaluacja modelu
    print("[5/6] Ewaluacja nowego modelu...")
    eval_result = await professor.process("oceń model")
    print(eval_result)
    print()

    # Krok 6: Porównanie i promocja
    print("[6/6] Porównanie wersji i promocja...")
    comparison = model_manager.compare_versions("v1.0", "v1.1")
    if comparison:
        print("   📊 Porównanie metryk:")
        for metric, data in comparison["metrics_diff"].items():
            if isinstance(data["diff"], (int, float)):
                print(
                    f"      {metric}: {data['v1']:.2f} → {data['v2']:.2f} "
                    f"({data['diff_pct']:+.1f}%)"
                )

    # Aktywuj lepszą wersję
    model_manager.activate_version("v1.1")
    print("   ✅ Aktywowano model v1.1")
    print()

    # Genealogia
    print("📜 Genealogia Inteligencji:")
    genealogy = model_manager.get_genealogy()
    print(f"   Liczba wersji: {genealogy['total_versions']}")
    print(f"   Aktywna wersja: {genealogy['active_version']}")
    print("   Historia:")
    for version in genealogy["versions"]:
        status = "🟢 AKTYWNA" if version["is_active"] else "⚪ Archiwalna"
        print(f"      {status} {version['version_id']} - {version['base_model']}")
        if version["performance_metrics"]:
            print(f"         Metryki: {version['performance_metrics']}")
    print()

    print("=" * 60)
    print("✅ DEMO ZAKOŃCZONE")
    print("=" * 60)
    print()
    print("Następne kroki:")
    print("1. Uruchom prawdziwy trening z GPU: professor.process('rozpocznij trening')")
    print("2. Monitoruj postęp: professor.process('sprawdź postęp treningu')")
    print("3. Integracja z Dashboard - wizualizacja w interfejsie web")
    print("4. Automatyzacja - dodaj do Scheduler dla cyklicznych treningów")


if __name__ == "__main__":
    asyncio.run(main())
