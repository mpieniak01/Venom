"""Moduł: vector_store - Baza wektorowa oparta na LanceDB."""

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from venom_core.config import SETTINGS
from venom_core.memory.embedding_service import EmbeddingService
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class VectorStore:
    """
    Baza wektorowa do przechowywania i wyszukiwania embeddingów.
    Używa LanceDB jako lokalnego embedded database.
    """

    def __init__(
        self,
        db_path: str = None,
        embedding_service: EmbeddingService = None,
        collection_name: str = "default",
    ):
        """
        Inicjalizacja VectorStore.

        Args:
            db_path: Ścieżka do katalogu bazy danych (domyślnie data/memory/lancedb)
            embedding_service: Serwis embeddingów (domyślnie nowa instancja)
            collection_name: Nazwa domyślnej kolekcji
        """
        self.db_path = Path(db_path or f"{SETTINGS.MEMORY_ROOT}/lancedb")
        self.db_path.mkdir(parents=True, exist_ok=True)

        self.embedding_service = embedding_service or EmbeddingService()
        self.collection_name = collection_name

        # Lazy loading bazy danych
        self._db = None
        self._table = None

        logger.info(f"VectorStore zainicjalizowany: db_path={self.db_path}")

    def _ensure_db_connected(self):
        """Lazy loading połączenia z bazą danych."""
        if self._db is not None:
            return

        try:
            import lancedb

            logger.info(f"Łączenie z bazą LanceDB: {self.db_path}")
            self._db = lancedb.connect(str(self.db_path))
            logger.info("Połączono z bazą LanceDB pomyślnie")
        except ImportError:
            logger.error("lancedb nie jest zainstalowany. Zainstaluj: pip install lancedb")
            raise

    def _get_or_create_table(self, collection_name: str = None):
        """
        Pobiera lub tworzy tabelę w bazie.

        Args:
            collection_name: Nazwa kolekcji/tabeli

        Returns:
            Tabela LanceDB
        """
        self._ensure_db_connected()
        col_name = collection_name or self.collection_name

        # Sprawdź czy tabela już istnieje
        if col_name in self._db.table_names():
            logger.debug(f"Używanie istniejącej tabeli: {col_name}")
            return self._db.open_table(col_name)

        # Utwórz nową tabelę z przykładowym schematem
        logger.info(f"Tworzenie nowej tabeli: {col_name}")
        
        # Pobierz wymiar embeddingu
        dim = self.embedding_service.embedding_dimension
        
        # Utwórz tabelę z przykładowym rekordem (LanceDB wymaga danych do schematu)
        dummy_embedding = [0.0] * dim
        data = [
            {
                "id": "init",
                "text": "Initialization record",
                "vector": dummy_embedding,
                "metadata": "{}",
            }
        ]
        
        table = self._db.create_table(col_name, data=data, mode="overwrite")
        logger.info(f"Tabela {col_name} utworzona pomyślnie")
        
        return table

    def create_collection(self, name: str) -> str:
        """
        Tworzy nową kolekcję (tabelę) w bazie.

        Args:
            name: Nazwa kolekcji

        Returns:
            Komunikat o sukcesie

        Raises:
            ValueError: Jeśli nazwa jest nieprawidłowa
        """
        if not name or not name.strip():
            raise ValueError("Nazwa kolekcji nie może być pusta")

        # Walidacja nazwy (tylko litery, cyfry, _, -)
        if not re.match(r"^[a-zA-Z0-9_-]+$", name):
            raise ValueError(
                "Nazwa kolekcji może zawierać tylko litery, cyfry, _ i -"
            )

        self._get_or_create_table(name)
        return f"Kolekcja '{name}' utworzona pomyślnie"

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """
        Dzieli tekst na mniejsze fragmenty z overlapem.

        Args:
            text: Tekst do podziału
            chunk_size: Rozmiar fragmentu w znakach
            overlap: Liczba znaków nakładania się między fragmentami

        Returns:
            Lista fragmentów tekstowych
        """
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]

            # Spróbuj zakończyć na końcu zdania lub słowa
            if end < len(text):
                # Szukaj ostatniej kropki, nowej linii lub spacji
                last_period = chunk.rfind(". ")
                last_newline = chunk.rfind("\n")
                last_space = chunk.rfind(" ")

                best_break = max(last_period, last_newline, last_space)
                if best_break > chunk_size * 0.5:  # Tylko jeśli nie za blisko początku
                    chunk = chunk[: best_break + 1]
                    end = start + len(chunk)

            chunks.append(chunk.strip())
            start = end - overlap

        return [c for c in chunks if c]  # Usuń puste fragmenty

    def upsert(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        collection_name: str = None,
        chunk_text: bool = True,
    ) -> str:
        """
        Zapisuje lub aktualizuje tekst w bazie wektorowej.

        Args:
            text: Tekst do zapisania
            metadata: Opcjonalne metadane (dict)
            collection_name: Nazwa kolekcji (domyślnie self.collection_name)
            chunk_text: Czy podzielić tekst na fragmenty

        Returns:
            Komunikat o sukcesie z liczbą zapisanych fragmentów

        Raises:
            ValueError: Jeśli tekst jest pusty
        """
        if not text or not text.strip():
            raise ValueError("Tekst nie może być pusty")

        metadata = metadata or {}
        col_name = collection_name or self.collection_name

        # Podziel tekst na fragmenty jeśli potrzeba
        if chunk_text and len(text) > 500:
            chunks = self._chunk_text(text)
            logger.info(f"Tekst podzielony na {len(chunks)} fragmentów")
        else:
            chunks = [text]

        # Generuj embeddingi dla wszystkich fragmentów
        embeddings = self.embedding_service.get_embeddings_batch(chunks)

        # Przygotuj dane do zapisu
        table = self._get_or_create_table(col_name)
        
        records = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            record = {
                "id": str(uuid.uuid4()),
                "text": chunk,
                "vector": embedding,
                "metadata": json.dumps(metadata),
            }
            records.append(record)

        # Dodaj do tabeli
        table.add(records)
        
        logger.info(
            f"Zapisano {len(records)} fragmentów do kolekcji '{col_name}'"
        )
        return f"Zapisano {len(records)} fragmentów do pamięci"

    def search(
        self, query: str, limit: int = 3, collection_name: str = None
    ) -> List[Dict[str, Any]]:
        """
        Wyszukuje najbardziej podobne fragmenty do zapytania.

        Args:
            query: Zapytanie tekstowe
            limit: Maksymalna liczba wyników
            collection_name: Nazwa kolekcji (domyślnie self.collection_name)

        Returns:
            Lista słowników z wynikami (text, metadata, score)

        Raises:
            ValueError: Jeśli zapytanie jest puste
        """
        if not query or not query.strip():
            raise ValueError("Zapytanie nie może być puste")

        col_name = collection_name or self.collection_name

        # Sprawdź czy tabela istnieje
        self._ensure_db_connected()
        if col_name not in self._db.table_names():
            logger.warning(f"Kolekcja '{col_name}' nie istnieje, zwracam pustą listę")
            return []

        table = self._db.open_table(col_name)

        # Generuj embedding dla zapytania
        query_embedding = self.embedding_service.get_embedding(query)

        # Wyszukaj najbliższe wektory
        logger.info(f"Wyszukiwanie w kolekcji '{col_name}' z limitem {limit}")
        results = table.search(query_embedding).limit(limit).to_list()

        # Przetwórz wyniki
        processed_results = []
        for result in results:
            # Pomiń rekord inicjalizacyjny
            if result.get("id") == "init":
                continue
                
            processed_results.append(
                {
                    "text": result["text"],
                    "metadata": json.loads(result.get("metadata", "{}")),
                    "score": result.get("_distance", 0.0),
                }
            )

        logger.info(f"Znaleziono {len(processed_results)} wyników")
        return processed_results

    def list_collections(self) -> List[str]:
        """
        Zwraca listę wszystkich kolekcji w bazie.

        Returns:
            Lista nazw kolekcji
        """
        self._ensure_db_connected()
        return self._db.table_names()

    def delete_collection(self, collection_name: str) -> str:
        """
        Usuwa kolekcję z bazy.

        Args:
            collection_name: Nazwa kolekcji do usunięcia

        Returns:
            Komunikat o sukcesie

        Raises:
            ValueError: Jeśli kolekcja nie istnieje
        """
        self._ensure_db_connected()
        
        if collection_name not in self._db.table_names():
            raise ValueError(f"Kolekcja '{collection_name}' nie istnieje")

        self._db.drop_table(collection_name)
        logger.info(f"Kolekcja '{collection_name}' usunięta")
        return f"Kolekcja '{collection_name}' usunięta pomyślnie"
