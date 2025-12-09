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
    MIN_NEW_LESSONS = 50  # Minimum nowych lekcji od ostatniego treningu

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

            # Policz liczbę przykładów w datasecie
            dataset_size = 0
            try:
                with open(dataset_path, "r", encoding="utf-8") as f:
                    dataset_size = sum(1 for line in f if line.strip())
            except Exception as e:
                logger.warning(f"Nie można policzyć przykładów w datasecie: {e}")

            # Dobierz parametry
            params = self._select_training_parameters(dataset_size=dataset_size)

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

            # Pobierz aktualną liczbę lekcji
            lessons_count = 0
            if self.lessons_store:
                stats = self.lessons_store.get_statistics()
                lessons_count = stats.get("total_lessons", 0)

            self.training_history.append(
                {
                    "job_name": job_info["job_name"],
                    "dataset_path": dataset_path,
                    "adapter_path": job_info.get("adapter_path"),
                    "params": params,
                    "status": "running",
                    "started_at": datetime.now().isoformat(),
                    "lessons_count": lessons_count,
                    "dataset_size": dataset_size,
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

    async def _evaluate_model(
        self,
        candidate_model: Optional[str] = None,
        baseline_model: Optional[
            str
        ] = None,  # Zarezerwowane na przyszłość (integracja porównania z modelem bazowym)
    ) -> str:
        """
        Ewaluuje nowy model (Arena - porównanie z poprzednią wersją).

        Args:
            candidate_model: Ścieżka do nowego modelu/adaptera (jeśli None, używa ostatniego z treningu)
            baseline_model: Ścieżka do modelu bazowego (jeśli None, używa produkcyjnego)

        Returns:
            Raport z ewaluacji
        """
        # Golden Dataset - pytania testowe
        golden_questions = [
            {
                "instruction": "Napisz funkcję w Pythonie, która oblicza silnię liczby.",
                "input": "n = 5",
            },
            {
                "instruction": "Wyjaśnij czym jest rekurencja w programowaniu.",
                "input": "",
            },
            {
                "instruction": "Popraw błąd w tym kodzie Python.",
                "input": "def hello():\nprint('Hello world')",
            },
        ]

        logger.info("Rozpoczynam ewaluację modelu w Arenie...")

        # Jeśli nie podano candidate_model, użyj ostatniego z treningu
        if not candidate_model and self.training_history:
            last_training = self.training_history[-1]
            if last_training.get("status") == "completed":
                # Sprawdź czy adapter istnieje
                from pathlib import Path

                adapter_path_str = last_training.get("adapter_path")
                if adapter_path_str:
                    adapter_path = Path(adapter_path_str)
                    if adapter_path.exists():
                        candidate_model = str(adapter_path)

        if not candidate_model:
            return "❌ Brak nowego modelu do ewaluacji. Przeprowadź trening najpierw."

        # Dla uproszczenia, używamy prostej metryki bez faktycznego uruchamiania modeli
        # (wymaga integracji z Ollama lub transformers)
        # W produkcji tutaj należy uruchomić oba modele i porównać odpowiedzi

        try:
            # Symulujemy ewaluację - sprawdzamy czy modele są dostępne
            candidate_available = self._check_model_availability(candidate_model)

            if not candidate_available:
                return f"❌ Model kandydujący nie jest dostępny: {candidate_model}"

            # Przeprowadź testy
            candidate_scores = []
            baseline_scores = []

            for i, question in enumerate(golden_questions):
                logger.info(f"Testowanie pytania {i + 1}/{len(golden_questions)}...")

                # W rzeczywistym systemie tutaj uruchamiamy modele
                # Na razie symulujemy wyniki na podstawie prostych metryk
                candidate_response = self._simulate_model_response(
                    question, "candidate"
                )
                baseline_response = self._simulate_model_response(question, "baseline")

                # Oceń odpowiedzi (prosta metryka: długość i obecność kodu)
                candidate_score = self._score_response(
                    candidate_response, question["instruction"]
                )
                baseline_score = self._score_response(
                    baseline_response, question["instruction"]
                )

                candidate_scores.append(candidate_score)
                baseline_scores.append(baseline_score)

            # Oblicz średnie wyniki
            if not candidate_scores or not baseline_scores:
                return "❌ Błąd: Brak wyników ewaluacji"

            avg_candidate = sum(candidate_scores) / len(candidate_scores)
            avg_baseline = sum(baseline_scores) / len(baseline_scores)

            # Oblicz improvement score z obsługą zerowej baseline
            if avg_baseline > 0:
                improvement_score = (avg_candidate - avg_baseline) / avg_baseline
            elif avg_candidate > 0:
                # Jeśli baseline=0 ale candidate>0, to 100% improvement
                improvement_score = 1.0
            else:
                # Oba zero - brak poprawy
                improvement_score = 0.0

            winner = "new_model" if avg_candidate > avg_baseline else "baseline_model"

            # Generuj raport
            report = (
                "🏟️ ARENA - Ewaluacja Modelu\n\n"
                f"📊 Wyniki:\n"
                f"- Model bazowy: {avg_baseline:.2f}/10\n"
                f"- Nowy model: {avg_candidate:.2f}/10\n"
                f"- Improvement: {improvement_score * 100:+.1f}%\n\n"
                f"🏆 Zwycięzca: {winner}\n\n"
                "📝 Szczegóły testów:\n"
            )

            for i, (q, c_score, b_score) in enumerate(
                zip(golden_questions, candidate_scores, baseline_scores)
            ):
                instruction_preview = q["instruction"][:50] + (
                    "..." if len(q["instruction"]) > 50 else ""
                )
                report += f"{i + 1}. {instruction_preview}\n"
                report += f"   Baseline: {b_score}/10, Candidate: {c_score}/10\n"

            if winner == "new_model" and improvement_score > 0.1:
                report += "\n✅ REKOMENDACJA: Promuj nowy model do produkcji"
            elif improvement_score > 0:
                report += "\n⚠️ REKOMENDACJA: Niewielka poprawa, rozważ więcej treningu"
            else:
                report += "\n❌ REKOMENDACJA: Zostań przy aktualnym modelu"

            return report

        except Exception as e:
            error_msg = f"❌ Błąd podczas ewaluacji: {e}"
            logger.error(error_msg)
            return error_msg

    def _check_model_availability(self, model_path: str) -> bool:
        """
        Sprawdza czy model jest dostępny.

        Args:
            model_path: Ścieżka do modelu

        Returns:
            True jeśli model jest dostępny
        """
        from pathlib import Path

        path = Path(model_path)
        return path.exists() and (path.is_dir() or path.is_file())

    def _simulate_model_response(
        self, question: Dict[str, str], model_type: str
    ) -> str:
        """
        Symuluje odpowiedź modelu (placeholder do zastąpienia rzeczywistym wywołaniem).

        Args:
            question: Pytanie testowe
            model_type: Typ modelu ('candidate' lub 'baseline')

        Returns:
            Symulowana odpowiedź
        """
        # W rzeczywistym systemie tutaj wywołujemy model przez Ollama/transformers
        # Na razie zwracamy symulowaną odpowiedź
        instruction = question["instruction"].lower()

        if "funkcję" in instruction or "function" in instruction:
            if model_type == "candidate":
                return "def factorial(n):\n    if n == 0:\n        return 1\n    return n * factorial(n-1)"
            else:
                return "def factorial(n):\n    result = 1\n    for i in range(1, n+1):\n        result *= i\n    return result"
        elif "rekurencja" in instruction or "recursion" in instruction:
            return "Rekurencja to technika programistyczna, gdzie funkcja wywołuje sama siebie."
        else:
            return "def hello():\n    print('Hello world')"

    def _score_response(self, response: str, instruction: str) -> float:
        """
        Ocenia jakość odpowiedzi (prosta heurystyka).

        Args:
            response: Odpowiedź modelu
            instruction: Instrukcja pytania

        Returns:
            Wynik w skali 0-10
        """
        score = 5.0  # Bazowy wynik

        # Czy odpowiedź nie jest pusta?
        if not response or len(response) < 10:
            return 1.0

        # Czy zawiera kod (jeśli pytanie dotyczy kodu)?
        if any(
            keyword in instruction.lower()
            for keyword in ["funkcję", "kod", "function", "code", "popraw"]
        ):
            if "def " in response or "class " in response or "import " in response:
                score += 2.0
            if "return" in response:
                score += 1.0

        # Czy odpowiedź jest wystarczająco długa?
        if len(response) > 50:
            score += 1.0
        if len(response) > 100:
            score += 1.0

        return min(score, 10.0)

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

        # Sprawdź interwał od ostatniego treningu (time-gating)
        if self.training_history:
            from datetime import datetime, timedelta

            last_training = self.training_history[-1]
            last_started_at = last_training.get("started_at")

            if last_started_at:
                try:
                    last_time = datetime.fromisoformat(last_started_at)
                    time_since_last = datetime.now() - last_time
                    min_interval = timedelta(hours=self.MIN_TRAINING_INTERVAL_HOURS)

                    if time_since_last < min_interval:
                        hours_remaining = (
                            min_interval - time_since_last
                        ).total_seconds() / 3600
                        return {
                            "should_train": False,
                            "reason": (
                                f"Zbyt wcześnie od ostatniego treningu. "
                                f"Poczekaj jeszcze {hours_remaining:.1f}h "
                                f"(minimum {self.MIN_TRAINING_INTERVAL_HOURS}h przerwy)."
                            ),
                        }
                except (ValueError, TypeError) as e:
                    logger.warning(f"Błąd parsowania timestamp: {e}")

            # Sprawdź przyrost lekcji od ostatniego treningu
            last_lessons_count = last_training.get("lessons_count", 0)
            new_lessons = total_lessons - last_lessons_count

            if new_lessons < self.MIN_NEW_LESSONS:
                return {
                    "should_train": False,
                    "reason": (
                        f"Za mało nowych lekcji od ostatniego treningu ({new_lessons}). "
                        f"Potrzeba minimum {self.MIN_NEW_LESSONS} nowych przykładów."
                    ),
                }

        return {
            "should_train": True,
            "reason": f"Zebrano {total_lessons} lekcji. Gotowy do treningu!",
        }

    def _select_training_parameters(self, dataset_size: int = 0) -> Dict[str, Any]:
        """
        Dobiera optymalne parametry treningowe.

        Args:
            dataset_size: Liczba przykładów w datasecie (0 = nie podano)

        Returns:
            Słownik z parametrami treningu
        """
        # Domyślne wartości
        batch_size = self.DEFAULT_BATCH_SIZE
        num_epochs = self.DEFAULT_NUM_EPOCHS
        learning_rate = self.DEFAULT_LEARNING_RATE

        # Tylko jeśli dataset_size został faktycznie podany (> 0)
        if dataset_size > 0:
            # Heurystyka #1: Dostosuj batch_size na podstawie rozmiaru datasetu
            if dataset_size > 1000:
                # Duży dataset -> większy batch size dla lepszego wykorzystania GPU
                batch_size = 8
            elif dataset_size > 500:
                batch_size = 6
            elif dataset_size < 100:
                # Mały dataset -> mniejszy batch size, aby uniknąć overfittingu
                batch_size = 2
            # Dla 100-500: używamy domyślnych wartości (batch_size=4)

            # Heurystyka #2: Dostosuj liczbę epok na podstawie rozmiaru datasetu
            if dataset_size < 100:
                # Mały dataset -> więcej epok, aby model dobrze się nauczył
                num_epochs = 5
            elif dataset_size > 1000:
                # Duży dataset -> mniej epok (model się szybciej uczy)
                num_epochs = 2
            # Dla 100-1000: używamy domyślnych wartości (num_epochs=3)

        # Heurystyka #3: Sprawdź dostępną VRAM (jeśli gpu_habitat dostępny)
        if self.gpu_habitat:
            try:
                import shutil
                import subprocess

                # Sprawdź czy nvidia-smi jest dostępny
                if shutil.which("nvidia-smi"):
                    result = subprocess.run(
                        [
                            "nvidia-smi",
                            "--query-gpu=memory.total",
                            "--format=csv,noheader,nounits",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,  # Nie rzucaj wyjątku przy niezerowym exit code
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        vram_lines = result.stdout.strip().split("\n")
                        vram_values = [int(line) for line in vram_lines if line.strip()]
                        if vram_values:
                            vram_mb = min(
                                vram_values
                            )  # Użyj minimalnej VRAM dla multi-GPU
                            vram_gb = vram_mb / 1024

                            if vram_gb < 8:
                                # Niska VRAM -> wymuś bardzo mały batch size
                                batch_size = min(batch_size, 1)
                                logger.info(
                                    f"Wykryto niską VRAM ({vram_gb:.1f}GB), ustawiono batch_size=1"
                                )
            except (ValueError, IndexError, subprocess.TimeoutExpired, OSError) as e:
                logger.debug(f"Nie można sprawdzić VRAM: {e}")

        logger.info(
            f"Dobrano parametry dla dataset_size={dataset_size}: "
            f"batch_size={batch_size}, num_epochs={num_epochs}, lr={learning_rate}"
        )

        return {
            "base_model": "unsloth/Phi-3-mini-4k-instruct",
            "lora_rank": self.DEFAULT_LORA_RANK,
            "learning_rate": learning_rate,
            "num_epochs": num_epochs,
            "max_seq_length": self.DEFAULT_MAX_SEQ_LENGTH,
            "batch_size": batch_size,
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
