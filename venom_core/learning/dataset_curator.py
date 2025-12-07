"""Moduł: dataset_curator - Kurator Danych dla Knowledge Distillation."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Konfiguracja domyślnych limitów
DEFAULT_MAX_DIFF_LENGTH = 1500  # Maksymalna długość diff w przykładzie treningowym
DEFAULT_MIN_QUALITY_SCORE = 0.5  # Minimalny wynik jakości


class TrainingExample:
    """
    Reprezentacja pojedynczego przykładu treningowego.
    Format kompatybilny z Alpaca/ShareGPT JSONL.
    """

    def __init__(
        self,
        instruction: str,
        input_text: str,
        output: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicjalizacja przykładu treningowego.

        Args:
            instruction: Instrukcja systemowa (co model ma zrobić)
            input_text: Wejście użytkownika (kontekst/pytanie)
            output: Oczekiwane wyjście modelu
            metadata: Dodatkowe metadane (źródło, tagi, timestamp, etc.)
        """
        self.instruction = instruction
        self.input_text = input_text
        self.output = output
        self.metadata = metadata or {}

    def to_alpaca_format(self) -> Dict[str, str]:
        """
        Konwertuje do formatu Alpaca.

        Returns:
            Słownik w formacie Alpaca (instruction, input, output)
        """
        return {
            "instruction": self.instruction,
            "input": self.input_text,
            "output": self.output,
        }

    def to_sharegpt_format(self) -> Dict[str, Any]:
        """
        Konwertuje do formatu ShareGPT (conversations).

        Returns:
            Słownik w formacie ShareGPT
        """
        return {
            "conversations": [
                {"from": "system", "value": self.instruction},
                {"from": "human", "value": self.input_text},
                {"from": "gpt", "value": self.output},
            ]
        }

    def to_dict(self) -> Dict[str, Any]:
        """
        Konwertuje do pełnego słownika z metadanymi.

        Returns:
            Pełny słownik z wszystkimi danymi
        """
        return {
            "instruction": self.instruction,
            "input": self.input_text,
            "output": self.output,
            "metadata": self.metadata,
        }


class DatasetCurator:
    """
    Kurator Danych - zarządza procesem tworzenia zbiorów treningowych.

    Konwertuje surowe dane (Lessons, Git History, Task History) w format
    treningowy JSONL kompatybilny z Unsloth/Hugging Face Fine-tuning.
    """

    def __init__(
        self,
        output_dir: str = None,
        lessons_store=None,
        git_skill=None,
        state_manager=None,
        min_quality_score: float = 0.5,
    ):
        """
        Inicjalizacja DatasetCurator.

        Args:
            output_dir: Katalog wyjściowy dla datasetów (domyślnie data/training/)
            lessons_store: Instancja LessonsStore (opcjonalne)
            git_skill: Instancja GitSkill (opcjonalne)
            state_manager: Instancja StateManager (opcjonalne)
            min_quality_score: Minimalny wynik jakości dla przykładów (0.0-1.0)
        """
        self.output_dir = Path(
            output_dir or f"{SETTINGS.WORKSPACE_ROOT}/../data/training"
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.lessons_store = lessons_store
        self.git_skill = git_skill
        self.state_manager = state_manager
        self.min_quality_score = min_quality_score

        self.examples: List[TrainingExample] = []

        logger.info(
            f"DatasetCurator zainicjalizowany (output_dir={self.output_dir}, "
            f"min_quality={min_quality_score})"
        )

    def collect_from_lessons(
        self, limit: Optional[int] = None, tags: Optional[List[str]] = None
    ) -> int:
        """
        Zbiera przykłady z LessonsStore.

        Args:
            limit: Maksymalna liczba lekcji do zebrania
            tags: Opcjonalne tagi do filtrowania

        Returns:
            Liczba zebranych przykładów
        """
        if not self.lessons_store:
            logger.warning("LessonsStore nie jest dostępny")
            return 0

        try:
            # Pobierz lekcje
            if tags:
                lessons = self.lessons_store.get_lessons_by_tags(tags)
            else:
                lessons = self.lessons_store.get_all_lessons(limit=limit)

            collected = 0
            for lesson in lessons:
                # Filtruj po wyniku (tylko sukcesy)
                if "sukces" not in lesson.result.lower() and "✅" not in lesson.result:
                    continue

                # Twórz przykład treningowy
                example = TrainingExample(
                    instruction="Jesteś asystentem AI Venom. Pomóż użytkownikowi rozwiązać problem.",
                    input_text=lesson.situation,
                    output=f"{lesson.action}\n\nRezultat: {lesson.result}\n\nLekcja: {lesson.feedback}",
                    metadata={
                        "source": "lessons_store",
                        "lesson_id": lesson.lesson_id,
                        "timestamp": lesson.timestamp,
                        "tags": lesson.tags,
                    },
                )

                self.examples.append(example)
                collected += 1

            logger.info(f"Zebrano {collected} przykładów z LessonsStore")
            return collected

        except Exception as e:
            logger.error(f"Błąd podczas zbierania z LessonsStore: {e}")
            return 0

    def collect_from_git_history(
        self, repo_path: Optional[str] = None, max_commits: int = 50
    ) -> int:
        """
        Zbiera przykłady z historii Git (Diff -> Commit Message).

        Args:
            repo_path: Ścieżka do repozytorium (domyślnie workspace)
            max_commits: Maksymalna liczba commitów do analizy

        Returns:
            Liczba zebranych przykładów
        """
        if not self.git_skill:
            logger.warning("GitSkill nie jest dostępny")
            return 0

        try:
            from git import Repo

            repo_path = repo_path or SETTINGS.WORKSPACE_ROOT
            repo = Repo(repo_path)

            collected = 0
            for commit in list(repo.iter_commits())[:max_commits]:
                # Pomiń merge commity i commity bez diff
                if len(commit.parents) > 1:
                    continue

                # Pobierz diff
                if commit.parents:
                    diff = repo.git.diff(commit.parents[0], commit, unified=3)
                else:
                    # Pierwszy commit
                    diff = repo.git.show(commit, format="", unified=3)

                # Pomiń zbyt duże diffy (konfigurowalny limit)
                if len(diff) > self.max_diff_length * 2:
                    continue

                # Pomiń puste diffy
                if not diff.strip():
                    continue

                # Twórz przykład treningowy (skróć diff do max_diff_length)
                example = TrainingExample(
                    instruction="Na podstawie zmian w kodzie (diff), wygeneruj opisową wiadomość commit.",
                    input_text=f"Diff:\n```\n{diff[: self.max_diff_length]}\n```",
                    output=commit.message.strip(),
                    metadata={
                        "source": "git_history",
                        "commit_sha": commit.hexsha,
                        "author": str(commit.author),
                        "timestamp": commit.committed_datetime.isoformat(),
                    },
                )

                self.examples.append(example)
                collected += 1

            logger.info(f"Zebrano {collected} przykładów z Git History")
            return collected

        except Exception as e:
            logger.error(f"Błąd podczas zbierania z Git History: {e}")
            return 0

    def collect_from_task_history(
        self, max_tasks: int = 50, only_completed: bool = True
    ) -> int:
        """
        Zbiera przykłady z historii zadań z StateManager.

        Args:
            max_tasks: Maksymalna liczba zadań do analizy
            only_completed: Czy zbierać tylko ukończone zadania

        Returns:
            Liczba zebranych przykładów
        """
        if not self.state_manager:
            logger.warning("StateManager nie jest dostępny")
            return 0

        try:
            # Pobierz zadania z state managera
            all_tasks = self.state_manager.get_all_tasks()

            collected = 0
            for task in list(all_tasks)[:max_tasks]:
                # Filtruj po statusie
                if only_completed and task.status != "completed":
                    continue

                # Pomiń zadania bez rezultatu
                if not task.result or len(task.result) < 20:
                    continue

                # Twórz przykład treningowy
                example = TrainingExample(
                    instruction="Jesteś asystentem AI Venom. Wykonaj zadanie użytkownika.",
                    input_text=task.request,
                    output=task.result,
                    metadata={
                        "source": "task_history",
                        "task_id": str(task.task_id),
                        "agent": task.assigned_agent,
                        "timestamp": (
                            task.created_at.isoformat() if task.created_at else None
                        ),
                    },
                )

                self.examples.append(example)
                collected += 1

            logger.info(f"Zebrano {collected} przykładów z Task History")
            return collected

        except Exception as e:
            logger.error(f"Błąd podczas zbierania z Task History: {e}")
            return 0

    def filter_low_quality(self) -> int:
        """
        Filtruje przykłady niskiej jakości.

        Kryteria:
        - Zbyt krótkie wejścia/wyjścia (< 10 znaków)
        - Duplikaty
        - Przykłady z błędami

        Returns:
            Liczba usuniętych przykładów
        """
        initial_count = len(self.examples)

        # Filtruj zbyt krótkie
        self.examples = [
            ex
            for ex in self.examples
            if len(ex.input_text) >= 10 and len(ex.output) >= 10
        ]

        # Usuń duplikaty (na podstawie input+output hash)
        seen = set()
        unique_examples = []
        for ex in self.examples:
            key = hash(ex.input_text + ex.output)
            if key not in seen:
                seen.add(key)
                unique_examples.append(ex)

        self.examples = unique_examples

        removed = initial_count - len(self.examples)
        if removed > 0:
            logger.info(f"Usunięto {removed} przykładów niskiej jakości")

        return removed

    def save_dataset(
        self, filename: Optional[str] = None, format: str = "alpaca"
    ) -> Path:
        """
        Zapisuje dataset do pliku JSONL.

        Args:
            filename: Nazwa pliku (domyślnie dataset_TIMESTAMP.jsonl)
            format: Format danych ('alpaca' lub 'sharegpt')

        Returns:
            Ścieżka do zapisanego pliku

        Raises:
            ValueError: Jeśli brak przykładów lub nieprawidłowy format
        """
        if not self.examples:
            raise ValueError("Brak przykładów do zapisania. Użyj collect_* najpierw.")

        if format not in ["alpaca", "sharegpt"]:
            raise ValueError(
                f"Nieznany format: {format}. Użyj 'alpaca' lub 'sharegpt'."
            )

        # Generuj nazwę pliku
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dataset_{format}_{timestamp}.jsonl"

        output_path = self.output_dir / filename

        # Zapisz do JSONL
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                for example in self.examples:
                    if format == "alpaca":
                        data = example.to_alpaca_format()
                    else:  # sharegpt
                        data = example.to_sharegpt_format()

                    f.write(json.dumps(data, ensure_ascii=False) + "\n")

            logger.info(
                f"Zapisano {len(self.examples)} przykładów do {output_path} "
                f"(format: {format})"
            )
            return output_path

        except Exception as e:
            logger.error(f"Błąd podczas zapisywania datasetu: {e}")
            raise

    def get_statistics(self) -> Dict[str, Any]:
        """
        Zwraca statystyki datasetu.

        Returns:
            Słownik ze statystykami
        """
        if not self.examples:
            return {"total_examples": 0}

        # Zlicz źródła
        sources = {}
        for ex in self.examples:
            source = ex.metadata.get("source", "unknown")
            sources[source] = sources.get(source, 0) + 1

        # Średnie długości
        avg_input_len = sum(len(ex.input_text) for ex in self.examples) / len(
            self.examples
        )
        avg_output_len = sum(len(ex.output) for ex in self.examples) / len(
            self.examples
        )

        return {
            "total_examples": len(self.examples),
            "sources": sources,
            "avg_input_length": round(avg_input_len, 2),
            "avg_output_length": round(avg_output_len, 2),
        }

    def clear(self) -> None:
        """Czyści zebrane przykłady."""
        self.examples.clear()
        logger.info("Wyczyszczono zebrane przykłady")
