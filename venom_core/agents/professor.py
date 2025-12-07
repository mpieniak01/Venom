"""Moduł: professor - Agent Profesor (Data Scientist i Opiekun Procesu Nauki)."""

from typing import Any, Dict, List, Optional

from semantic_kernel import Kernel

from venom_core.agents.base import BaseAgent
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class Professor(BaseAgent):
    """
    Agent Profesor - Data Scientist i Opiekun Procesu Nauki.

    Rola:
    - Decyduje kiedy uruchomić trening (na podstawie liczby nowych lekcji)
    - Dobiera parametry treningowe (learning rate, epochs, LoRA rank)
    - Ewaluuje nowe modele (Arena - porównanie z poprzednią wersją)
    - Promuje lepsze modele do produkcji
    """

    # Progi decyzyjne
    MIN_LESSONS_FOR_TRAINING = 100  # Minimum lekcji do rozpoczęcia treningu
    MIN_TRAINING_INTERVAL_HOURS = 24  # Minimum godzin między treningami

    # Domyślne parametry treningowe
    DEFAULT_LORA_RANK = 16
    DEFAULT_LEARNING_RATE = 2e-4
    DEFAULT_NUM_EPOCHS = 3
    DEFAULT_MAX_SEQ_LENGTH = 2048
    DEFAULT_BATCH_SIZE = 4

    def __init__(
        self,
        kernel: Kernel,
        dataset_curator=None,
        gpu_habitat=None,
        lessons_store=None,
    ):
        """
        Inicjalizacja Profesora.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            dataset_curator: Instancja DatasetCurator
            gpu_habitat: Instancja GPUHabitat
            lessons_store: Instancja LessonsStore
        """
        super().__init__(kernel)
        self.dataset_curator = dataset_curator
        self.gpu_habitat = gpu_habitat
        self.lessons_store = lessons_store

        # Historia treningów
        self.training_history: List[Dict[str, Any]] = []

        logger.info("Agent Professor zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza wejście i zwraca wynik.

        Rozpoznaje komendy:
        - "przygotuj materiały do nauki" - generuje dataset
        - "rozpocznij trening" - uruchamia trening
        - "sprawdź postęp treningu" - status treningu
        - "oceń model" - ewaluacja modelu

        Args:
            input_text: Treść zadania

        Returns:
            Wynik przetwarzania zadania
        """
        input_lower = input_text.lower()

        try:
            if "przygotuj materiały" in input_lower or "dataset" in input_lower:
                return await self._generate_dataset()

            elif "rozpocznij trening" in input_lower or "train" in input_lower:
                return await self._start_training()

            elif "sprawdź postęp" in input_lower or "status" in input_lower:
                return await self._check_training_status()

            elif "oceń model" in input_lower or "ewaluacja" in input_lower:
                return await self._evaluate_model()

            else:
                return (
                    "Jestem Profesorem - opiekujem się procesem nauki Venoma.\n\n"
                    "Mogę:\n"
                    "- Przygotować materiały do nauki (dataset)\n"
                    "- Rozpocząć trening modelu\n"
                    "- Sprawdzić postęp treningu\n"
                    "- Ocenić jakość nowego modelu\n\n"
                    f"Status: {self._get_learning_status()}"
                )

        except Exception as e:
            error_msg = f"❌ Błąd podczas przetwarzania: {e}"
            logger.error(error_msg)
            return error_msg

    async def _generate_dataset(self) -> str:
        """
        Generuje dataset treningowy.

        Returns:
            Raport z generacji datasetu
        """
        if not self.dataset_curator:
            return "❌ DatasetCurator nie jest dostępny"

        try:
            logger.info("Rozpoczynam generację datasetu...")

            # Wyczyść poprzednie przykłady
            self.dataset_curator.clear()

            # Zbierz dane z różnych źródeł
            lessons_count = self.dataset_curator.collect_from_lessons(limit=200)
            git_count = self.dataset_curator.collect_from_git_history(max_commits=100)

            # Filtruj niską jakość
            removed = self.dataset_curator.filter_low_quality()

            # Zapisz dataset
            dataset_path = self.dataset_curator.save_dataset(format="alpaca")

            # Statystyki
            stats = self.dataset_curator.get_statistics()

            report = (
                "✅ Dataset wygenerowany pomyślnie!\n\n"
                f"📊 Statystyki:\n"
                f"- Łączna liczba przykładów: {stats['total_examples']}\n"
                f"- Z LessonsStore: {lessons_count}\n"
                f"- Z Git History: {git_count}\n"
                f"- Usunięto (niska jakość): {removed}\n\n"
                f"- Średnia długość input: {stats['avg_input_length']} znaków\n"
                f"- Średnia długość output: {stats['avg_output_length']} znaków\n\n"
                f"📁 Lokalizacja: {dataset_path}\n\n"
            )

            if stats["total_examples"] >= 50:
                report += "✅ Dataset spełnia minimum (50 przykładów) i jest gotowy do treningu!"
            else:
                report += (
                    f"⚠️ Dataset ma tylko {stats['total_examples']} przykładów. "
                    f"Potrzeba minimum 50 do treningu."
                )

            return report

        except Exception as e:
            error_msg = f"❌ Błąd podczas generacji datasetu: {e}"
            logger.error(error_msg)
            return error_msg

    async def _start_training(self, dataset_path: Optional[str] = None) -> str:
        """
        Rozpoczyna trening modelu.

        Args:
            dataset_path: Opcjonalna ścieżka do datasetu (jeśli None, używa ostatniego)

        Returns:
            Raport z rozpoczęcia treningu
        """
        if not self.gpu_habitat:
            return "❌ GPUHabitat nie jest dostępny"

        try:
            # Jeśli nie podano ścieżki, znajdź ostatni dataset
            if not dataset_path:
                from pathlib import Path

                training_dir = Path("./data/training")
                if not training_dir.exists():
                    return "❌ Brak datasetu. Użyj 'przygotuj materiały do nauki' najpierw."

                datasets = sorted(training_dir.glob("dataset_*.jsonl"))
                if not datasets:
                    return "❌ Brak datasetu. Użyj 'przygotuj materiały do nauki' najpierw."

                dataset_path = str(datasets[-1])

            # Sprawdź czy powinniśmy trenować
            decision = self.should_start_training()
            if not decision["should_train"]:
                return f"⚠️ Nie spełniono kryteriów dla treningu:\n{decision['reason']}"

            # Dobierz parametry
            params = self._select_training_parameters()

            logger.info(f"Rozpoczynam trening z parametrami: {params}")

            # Uruchom trening
            from pathlib import Path

            output_dir = (
                Path("./data/models") / f"training_{len(self.training_history)}"
            )

            job_info = self.gpu_habitat.run_training_job(
                dataset_path=dataset_path,
                base_model=params["base_model"],
                output_dir=str(output_dir),
                lora_rank=params["lora_rank"],
                learning_rate=params["learning_rate"],
                num_epochs=params["num_epochs"],
                max_seq_length=params["max_seq_length"],
                batch_size=params["batch_size"],
            )

            # Zapisz w historii
            from datetime import datetime

            self.training_history.append(
                {
                    "job_name": job_info["job_name"],
                    "dataset_path": dataset_path,
                    "params": params,
                    "status": "running",
                    "started_at": datetime.now().isoformat(),
                }
            )

            report = (
                "✅ Trening rozpoczęty!\n\n"
                f"🏋️ Job: {job_info['job_name']}\n"
                f"📦 Kontener: {job_info['container_id'][:12]}\n"
                f"📊 Dataset: {Path(dataset_path).name}\n\n"
                f"⚙️ Parametry:\n"
                f"- Model bazowy: {params['base_model']}\n"
                f"- LoRA rank: {params['lora_rank']}\n"
                f"- Learning rate: {params['learning_rate']}\n"
                f"- Epoki: {params['num_epochs']}\n"
                f"- Batch size: {params['batch_size']}\n\n"
                f"📁 Adapter zostanie zapisany w: {job_info['adapter_path']}\n\n"
                "Użyj 'sprawdź postęp treningu' aby monitorować."
            )

            return report

        except Exception as e:
            error_msg = f"❌ Błąd podczas rozpoczynania treningu: {e}"
            logger.error(error_msg)
            return error_msg

    async def _check_training_status(self) -> str:
        """
        Sprawdza status aktualnego treningu.

        Returns:
            Raport ze statusem
        """
        if not self.training_history:
            return "ℹ️ Brak aktywnych treningów"

        try:
            # Pobierz ostatni trening
            last_training = self.training_history[-1]
            job_name = last_training["job_name"]

            # Sprawdź status
            status_info = self.gpu_habitat.get_training_status(job_name)

            # Aktualizuj status w historii
            last_training["status"] = status_info["status"]

            report = (
                f"📊 Status treningu: {job_name}\n\n"
                f"Status: {status_info['status'].upper()}\n"
                f"Kontener: {status_info['container_id'][:12]}\n\n"
                f"📜 Ostatnie logi:\n"
                f"```\n{status_info['logs'][-500:]}\n```\n"
            )

            if status_info["status"] == "completed":
                report += "\n✅ Trening zakończony! Możesz ocenić nowy model."
            elif status_info["status"] == "failed":
                report += "\n❌ Trening zakończył się błędem. Sprawdź logi."

            return report

        except Exception as e:
            error_msg = f"❌ Błąd podczas sprawdzania statusu: {e}"
            logger.error(error_msg)
            return error_msg

    async def _evaluate_model(self) -> str:
        """
        Ewaluuje nowy model (Arena - porównanie z poprzednią wersją).

        Returns:
            Raport z ewaluacji
        """
        # TODO: Implementacja Arena - zestawu testów porównawczych
        # Mockowy raport na razie
        report = (
            "🏟️ ARENA - Ewaluacja Modelu\n\n"
            "⚠️ Funkcjonalność w rozwoju\n\n"
            "Plan:\n"
            "1. Uruchomienie zestawu testów (10 pytań kodowania)\n"
            "2. Porównanie odpowiedzi: Stary Model vs Nowy Model\n"
            "3. Ocena jakości (human eval lub automated metrics)\n"
            "4. Decyzja o promocji\n\n"
            "Mock Result:\n"
            "- Stary Model: 7/10 poprawnych\n"
            "- Nowy Model: 8/10 poprawnych\n"
            "- Improvement: +14%\n\n"
            "✅ REKOMENDACJA: Promuj nowy model do produkcji"
        )

        return report

    def should_start_training(self) -> Dict[str, Any]:
        """
        Decyduje czy powinno się rozpocząć trening.

        Returns:
            Słownik z decyzją:
            - should_train: bool
            - reason: str (wyjaśnienie)
        """
        if not self.lessons_store:
            return {
                "should_train": False,
                "reason": "LessonsStore nie jest dostępny",
            }

        # Sprawdź liczbę nowych lekcji
        stats = self.lessons_store.get_statistics()
        total_lessons = stats.get("total_lessons", 0)

        if total_lessons < self.MIN_LESSONS_FOR_TRAINING:
            return {
                "should_train": False,
                "reason": (
                    f"Za mało lekcji ({total_lessons}). "
                    f"Potrzeba minimum {self.MIN_LESSONS_FOR_TRAINING}."
                ),
            }

        # TODO: Sprawdź interwał od ostatniego treningu
        # (wymaga zapisywania timestampów w training_history)

        return {
            "should_train": True,
            "reason": f"Zebrano {total_lessons} lekcji. Gotowy do treningu!",
        }

    def _select_training_parameters(self) -> Dict[str, Any]:
        """
        Dobiera optymalne parametry treningowe.

        Returns:
            Słownik z parametrami treningu
        """
        # TODO: Inteligentny dobór parametrów na podstawie:
        # - Rozmiaru datasetu
        # - Dostępnej VRAM
        # - Wcześniejszych wyników

        # Na razie zwracamy domyślne parametry
        return {
            "base_model": "unsloth/Phi-3-mini-4k-instruct",
            "lora_rank": self.DEFAULT_LORA_RANK,
            "learning_rate": self.DEFAULT_LEARNING_RATE,
            "num_epochs": self.DEFAULT_NUM_EPOCHS,
            "max_seq_length": self.DEFAULT_MAX_SEQ_LENGTH,
            "batch_size": self.DEFAULT_BATCH_SIZE,
        }

    def _get_learning_status(self) -> str:
        """
        Zwraca aktualny status systemu uczenia.

        Returns:
            Tekstowy status
        """
        if not self.lessons_store:
            return "LessonsStore niedostępny"

        stats = self.lessons_store.get_statistics()
        total_lessons = stats.get("total_lessons", 0)

        trainings_count = len(self.training_history)

        return (
            f"{total_lessons} lekcji zebrano, "
            f"{trainings_count} treningów przeprowadzono"
        )
