"""Moduł: lessons_store - Magazyn Lekcji i Meta-Uczenia."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class Lesson:
    """
    Reprezentacja pojedynczej lekcji (doświadczenia).
    """

    def __init__(
        self,
        situation: str,
        action: str,
        result: str,
        feedback: str,
        lesson_id: str = None,
        timestamp: str = None,
        tags: List[str] = None,
        metadata: Dict[str, Any] = None,
    ):
        """
        Inicjalizacja lekcji.

        Args:
            situation: Opis sytuacji/zadania
            action: Co zostało zrobione
            result: Rezultat (sukces/błąd)
            feedback: Co poprawić/czego się nauczyliśmy
            lesson_id: Unikalny identyfikator (generowany automatycznie jeśli None)
            timestamp: Timestamp (generowany automatycznie jeśli None)
            tags: Tagi do kategoryzacji
            metadata: Dodatkowe metadane
        """
        self.lesson_id = lesson_id or str(uuid.uuid4())
        self.timestamp = timestamp or datetime.now().isoformat()
        self.situation = situation
        self.action = action
        self.result = result
        self.feedback = feedback
        self.tags = tags or []
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje lekcję do słownika."""
        return {
            "lesson_id": self.lesson_id,
            "timestamp": self.timestamp,
            "situation": self.situation,
            "action": self.action,
            "result": self.result,
            "feedback": self.feedback,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    def to_text(self) -> str:
        """
        Konwertuje lekcję do reprezentacji tekstowej (dla embedowania).

        Returns:
            Tekstowa reprezentacja lekcji
        """
        text_parts = [
            f"Sytuacja: {self.situation}",
            f"Akcja: {self.action}",
            f"Rezultat: {self.result}",
            f"Lekcja: {self.feedback}",
        ]

        if self.tags:
            text_parts.append(f"Tagi: {', '.join(self.tags)}")

        return "\n".join(text_parts)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Lesson":
        """
        Tworzy lekcję ze słownika.

        Args:
            data: Słownik z danymi lekcji

        Returns:
            Instancja Lesson
        """
        return cls(
            lesson_id=data.get("lesson_id"),
            timestamp=data.get("timestamp"),
            situation=data["situation"],
            action=data["action"],
            result=data["result"],
            feedback=data["feedback"],
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


class LessonsStore:
    """
    Magazyn lekcji Venoma.
    Przechowuje doświadczenia i umożliwia semantyczne wyszukiwanie.
    """

    def __init__(
        self,
        storage_path: str = None,
        vector_store=None,
        auto_save: bool = True,
    ):
        """
        Inicjalizacja LessonsStore.

        Args:
            storage_path: Ścieżka do pliku z lekcjami (domyślnie data/memory/lessons.json)
            vector_store: Instancja VectorStore do indeksowania (opcjonalne)
            auto_save: Czy automatycznie zapisywać po każdej zmianie (domyślnie True)
        """
        self.storage_path = Path(storage_path or f"{SETTINGS.MEMORY_ROOT}/lessons.json")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self.vector_store = vector_store
        self.lessons: Dict[str, Lesson] = {}
        self.auto_save = auto_save

        # Ładuj istniejące lekcje
        self.load_lessons()

        logger.info(f"LessonsStore zainicjalizowany: {len(self.lessons)} lekcji")

    def add_lesson(
        self,
        situation: str,
        action: str,
        result: str,
        feedback: str,
        tags: List[str] = None,
        metadata: Dict[str, Any] = None,
    ) -> Lesson:
        """
        Dodaje nową lekcję.

        Args:
            situation: Opis sytuacji/zadania
            action: Co zostało zrobione
            result: Rezultat (sukces/błąd)
            feedback: Co poprawić/czego się nauczyliśmy
            tags: Tagi do kategoryzacji
            metadata: Dodatkowe metadane

        Returns:
            Utworzona lekcja
        """
        lesson = Lesson(
            situation=situation,
            action=action,
            result=result,
            feedback=feedback,
            tags=tags,
            metadata=metadata,
        )

        # Zapisz w pamięci
        self.lessons[lesson.lesson_id] = lesson

        # Indeksuj w vector store jeśli dostępny
        if self.vector_store:
            try:
                lesson_text = lesson.to_text()
                self.vector_store.upsert(
                    text=lesson_text,
                    metadata={
                        "lesson_id": lesson.lesson_id,
                        "category": "lesson",
                        "timestamp": lesson.timestamp,
                        "tags": ",".join(lesson.tags) if lesson.tags else "",
                    },
                    chunk_text=False,  # Lekcje są zwykle krótkie
                )
                logger.debug(f"Lekcja {lesson.lesson_id} zaindeksowana w vector store")
            except Exception as e:
                logger.warning(f"Nie udało się zaindeksować lekcji: {e}")

        # Zapisz na dysku jeśli auto_save włączone
        if self.auto_save:
            self.save_lessons()

        logger.info(f"Dodano nową lekcję: {lesson.lesson_id}")
        return lesson

    def get_lesson(self, lesson_id: str) -> Optional[Lesson]:
        """
        Pobiera lekcję po ID.

        Args:
            lesson_id: ID lekcji

        Returns:
            Lekcja lub None jeśli nie znaleziono
        """
        return self.lessons.get(lesson_id)

    def search_lessons(
        self, query: str, limit: int = 3, tags: List[str] = None
    ) -> List[Lesson]:
        """
        Wyszukuje lekcje semantycznie.

        Args:
            query: Zapytanie tekstowe
            limit: Maksymalna liczba wyników
            tags: Opcjonalne tagi do filtrowania

        Returns:
            Lista znalezionych lekcji
        """
        if not self.vector_store:
            logger.warning("Vector store nie jest dostępny, zwracam puste wyniki")
            return []

        try:
            # Wyszukaj w vector store
            results = self.vector_store.search(query, limit=limit * 2)  # Pobierz więcej

            # Filtruj po tagach jeśli podano
            lessons = []
            for result in results:
                metadata = result.get("metadata", {})
                lesson_id = metadata.get("lesson_id")

                if lesson_id and lesson_id in self.lessons:
                    lesson = self.lessons[lesson_id]

                    # Filtruj po tagach
                    if tags:
                        if not any(tag in lesson.tags for tag in tags):
                            continue

                    lessons.append(lesson)

                    if len(lessons) >= limit:
                        break

            logger.info(f"Znaleziono {len(lessons)} lekcji dla zapytania: {query[:50]}")
            return lessons

        except Exception as e:
            logger.error(f"Błąd podczas wyszukiwania lekcji: {e}")
            return []

    def get_all_lessons(self, limit: int = None) -> List[Lesson]:
        """
        Pobiera wszystkie lekcje.

        Args:
            limit: Opcjonalny limit wyników

        Returns:
            Lista lekcji (sortowana od najnowszych)
        """
        all_lessons = sorted(
            self.lessons.values(), key=lambda lesson: lesson.timestamp, reverse=True
        )

        if limit:
            return all_lessons[:limit]

        return all_lessons

    def get_lessons_by_tags(self, tags: List[str]) -> List[Lesson]:
        """
        Pobiera lekcje po tagach.

        Args:
            tags: Lista tagów

        Returns:
            Lista lekcji zawierających przynajmniej jeden z tagów
        """
        matching_lessons = []
        for lesson in self.lessons.values():
            if any(tag in lesson.tags for tag in tags):
                matching_lessons.append(lesson)

        return sorted(
            matching_lessons, key=lambda lesson: lesson.timestamp, reverse=True
        )

    def delete_lesson(self, lesson_id: str) -> bool:
        """
        Usuwa lekcję.

        Args:
            lesson_id: ID lekcji do usunięcia

        Returns:
            True jeśli usunięto, False jeśli nie znaleziono
        """
        if lesson_id in self.lessons:
            del self.lessons[lesson_id]
            if self.auto_save:
                self.save_lessons()
            logger.info(f"Usunięto lekcję: {lesson_id}")
            return True

        logger.warning(f"Nie znaleziono lekcji do usunięcia: {lesson_id}")
        return False

    def flush(self) -> None:
        """
        Wymusza zapis lekcji na dysku.
        Użyteczne gdy auto_save=False i chcemy ręcznie zapisać zmiany.
        """
        self.save_lessons()
        logger.info("Wymuszono zapis lekcji na dysku")

    def save_lessons(self) -> None:
        """Zapisuje lekcje do pliku JSON."""
        try:
            data = {
                "lessons": [lesson.to_dict() for lesson in self.lessons.values()],
                "count": len(self.lessons),
                "last_updated": datetime.now().isoformat(),
            }

            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Zapisano {len(self.lessons)} lekcji do {self.storage_path}")
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania lekcji: {e}")

    def load_lessons(self) -> None:
        """Ładuje lekcje z pliku JSON."""
        if not self.storage_path.exists():
            logger.info("Plik lekcji nie istnieje, rozpoczynam z pustym magazynem")
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            lessons_data = data.get("lessons", [])
            self.lessons = {
                lesson_data["lesson_id"]: Lesson.from_dict(lesson_data)
                for lesson_data in lessons_data
            }

            logger.info(f"Załadowano {len(self.lessons)} lekcji z {self.storage_path}")
        except Exception as e:
            logger.error(f"Błąd podczas ładowania lekcji: {e}")
            self.lessons = {}

    def get_statistics(self) -> Dict[str, Any]:
        """
        Zwraca statystyki magazynu lekcji.

        Returns:
            Słownik ze statystykami
        """
        all_tags = []
        for lesson in self.lessons.values():
            all_tags.extend(lesson.tags)

        tag_counts = {}
        for tag in all_tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

        return {
            "total_lessons": len(self.lessons),
            "unique_tags": len(set(all_tags)),
            "tag_distribution": tag_counts,
            "oldest_lesson": min(
                (lesson.timestamp for lesson in self.lessons.values()), default=None
            ),
            "newest_lesson": max(
                (lesson.timestamp for lesson in self.lessons.values()), default=None
            ),
        }
