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


class UpsertResult(str):
    """Wynik operacji upsert: zachowuje się jak string + dict-like access."""

    _chunks_count: int
    __slots__ = ("_chunks_count",)

    def __new__(cls, message: str, chunks_count: int):
        obj = str.__new__(cls, message)
        obj._chunks_count = chunks_count
        return obj

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            if key == "message":
                return str(self)
            if key == "chunks_count":
                return self._chunks_count
            raise KeyError(key)
        return str.__getitem__(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self) -> tuple[str, str]:
        return ("message", "chunks_count")

    def items(self) -> tuple[tuple[str, str], tuple[str, int]]:
        return (("message", str(self)), ("chunks_count", self._chunks_count))

    @property
    def message(self) -> str:
        return str(self)

    @property
    def chunks_count(self) -> int:
        return self._chunks_count


# Stałe dla chunkingu
DEFAULT_CHUNK_SIZE = 500  # Domyślny rozmiar fragmentu tekstu w znakach
DEFAULT_CHUNK_OVERLAP = 50  # Domyślne nakładanie się fragmentów w znakach
MIN_CHUNK_RATIO = 0.5  # Minimalny stosunek długości fragmentu do rozmiaru, aby zaakceptować punkt łamania


class VectorStore:
    """
    Baza wektorowa do przechowywania i wyszukiwania embeddingów.
    Używa LanceDB jako lokalnego embedded database.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        embedding_service: Optional[EmbeddingService] = None,
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
        self._db: Any = None
        self._table: Any = None

        logger.info(f"VectorStore zainicjalizowany: db_path={self.db_path}")

    def _ensure_db_connected(self) -> None:
        """Lazy loading połączenia z bazą danych."""
        if self._db is not None:
            return

        try:
            import lancedb  # type: ignore[import-untyped]

            logger.info(f"Łączenie z bazą LanceDB: {self.db_path}")
            self._db = lancedb.connect(str(self.db_path))
            logger.info("Połączono z bazą LanceDB pomyślnie")
        except ImportError:
            logger.error(
                "lancedb nie jest zainstalowany. Zainstaluj: pip install lancedb"
            )
            raise

    def _get_or_create_table(self, collection_name: Optional[str] = None):
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
        if self._db is None:
            raise RuntimeError("LanceDB connection not initialized")
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
            raise ValueError("Nazwa kolekcji może zawierać tylko litery, cyfry, _ i -")

        self._get_or_create_table(name)
        return f"Kolekcja '{name}' utworzona pomyślnie"

    def _chunk_text(
        self,
        text: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> List[str]:
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
                # Akceptuj punkt łamania tylko jeśli jest przynajmniej w połowie chunka
                # (zapobiega tworzeniu zbyt małych fragmentów)
                if best_break > chunk_size * MIN_CHUNK_RATIO:
                    chunk = chunk[: best_break + 1]
                    end = start + len(chunk)

            chunks.append(chunk.strip())
            start = end - overlap

        return [c for c in chunks if c]  # Usuń puste fragmenty

    def upsert(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        collection_name: Optional[str] = None,
        chunk_text: bool = True,
        id_override: Optional[str] = None,
    ) -> UpsertResult:
        """
        Zapisuje lub aktualizuje tekst w bazie wektorowej.

        Args:
            text: Tekst do zapisania
            metadata: Opcjonalne metadane (dict)
            collection_name: Nazwa kolekcji (domyślnie self.collection_name)
            chunk_text: Czy podzielić tekst na fragmenty

        Returns:
            UpsertResult – zachowuje się jak dict (`result["chunks_count"]`) i string
            (np. `\"zapisano\" in result.lower()`).

        Raises:
            ValueError: Jeśli tekst jest pusty
        """
        if not text or not text.strip():
            raise ValueError("Tekst nie może być pusty")

        metadata = metadata or {}
        col_name = collection_name or self.collection_name

        # Podziel tekst na fragmenty jeśli potrzeba
        if chunk_text and len(text) > DEFAULT_CHUNK_SIZE:
            chunks = self._chunk_text(text)
            logger.info(f"Tekst podzielony na {len(chunks)} fragmentów")
        else:
            chunks = [text]

        # Generuj embeddingi dla wszystkich fragmentów
        embeddings = self.embedding_service.get_embeddings_batch(chunks)

        # Przygotuj dane do zapisu
        table = self._get_or_create_table(col_name)

        records: list[dict[str, Any]] = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            record = {
                "id": id_override if id_override and i == 0 else str(uuid.uuid4()),
                "text": chunk,
                "vector": embedding,
                "metadata": json.dumps(metadata),
            }
            records.append(record)

        # Dodaj do tabeli
        table.add(records)

        logger.info(f"Zapisano {len(records)} fragmentów do kolekcji '{col_name}'")
        message = f"Zapisano {len(records)} fragmentów do pamięci"
        return UpsertResult(message=message, chunks_count=len(records))

    def search(
        self, query: str, limit: int = 3, collection_name: Optional[str] = None
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
            raise ValueError("Zapytanie nie może być puste (pusty prompt niedozwolony)")

        col_name = collection_name or self.collection_name

        # Sprawdź czy tabela istnieje
        self._ensure_db_connected()
        if self._db is None:
            raise RuntimeError("LanceDB connection not initialized")
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
        processed_results: list[dict[str, object]] = []
        for result in results:
            # Pomiń rekord inicjalizacyjny
            if result.get("id") == "init":
                continue

            processed_results.append(
                {
                    "text": result["text"],
                    "metadata": json.loads(result.get("metadata", "{}")),
                    "score": result.get("_distance"),
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
        if self._db is None:
            return []
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
        if self._db is None:
            raise RuntimeError("LanceDB connection not initialized")
        if collection_name not in self._db.table_names():
            raise ValueError(f"Kolekcja '{collection_name}' nie istnieje")

        self._db.drop_table(collection_name)
        logger.info(f"Kolekcja '{collection_name}' usunięta")
        return f"Kolekcja '{collection_name}' usunięta pomyślnie"

    def delete_by_metadata(
        self, filters: Dict[str, Any], collection_name: Optional[str] = None
    ) -> int:
        """
        Usuwa rekordy na podstawie dopasowania metadanych (proste wyszukiwanie substringów w kolumnie JSON).

        Args:
            filters: słownik klucz→wartość, który musi wystąpić w metadacie
            collection_name: opcjonalna nazwa kolekcji (domyślna, jeśli None)

        Returns:
            Szacowana liczba usuniętych rekordów (porównanie count przed/po).
        """
        if not filters:
            raise ValueError("filters nie może być puste przy delete_by_metadata")

        table = self._get_or_create_table(collection_name)

        # Walidacja i sanityzacja kluczy i wartości
        # UWAGA: LanceDB (w aktualnej wersji) nie wspiera tutaj zapytań
        # parametryzowanych, więc jako obejście stosujemy bardzo restrykcyjny
        # whitelisting znaków + escapowanie (defense in depth). Nie jest to
        # pełnoprawny zamiennik zapytań parametryzowanych – gdy tylko API
        # LanceDB to umożliwi, ten kod powinien zostać przerobiony na
        # podejście z parametryzacją.
        conditions = []
        MAX_KEY_LENGTH = 64
        MAX_VALUE_LENGTH = 256

        for key, value in filters.items():
            if value is None:
                continue

            # Walidacja klucza: tylko alfanumeryczne + underscore, max 64 znaki
            if not isinstance(key, str) or len(key) > MAX_KEY_LENGTH:
                raise ValueError(f"Nieprawidłowy klucz metadanych: {key}")
            if not re.match(r"^[a-zA-Z0-9_]+$", key):
                raise ValueError(f"Klucz metadanych zawiera niedozwolone znaki: {key}")

            # Walidacja typu wartości i konwersja na string
            if not isinstance(value, (str, int, float, bool)):
                raise TypeError(
                    f"Nieobsługiwany typ wartości dla klucza {key}: {type(value).__name__}. "
                    "Dozwolone typy: str, int, float, bool."
                )
            str_value = str(value)
            if len(str_value) > MAX_VALUE_LENGTH:
                raise ValueError(
                    f"Wartość dla klucza {key} przekracza maksymalną długość {MAX_VALUE_LENGTH} "
                    f"(otrzymano {len(str_value)} znaków)"
                )

            # Bardzo restrykcyjna walidacja: tylko alfanumeryczne, dash, dot, underscore
            # Celowo NIE dopuszczamy spacji ani znaków specjalnych
            if not re.match(r"^[a-zA-Z0-9_.\-]+$", str_value):
                raise ValueError(
                    f"Wartość dla klucza {key} zawiera niedozwolone znaki. "
                    f"Dozwolone: a-z, A-Z, 0-9, _, -, ."
                )

            # Podwójne escapowanie mimo walidacji (defense in depth)
            safe_value = (
                str_value.replace("\\", "\\\\").replace("'", "''").replace('"', '\\"')
            )
            conditions.append(f'metadata LIKE \'%\\"{key}\\": \\"{safe_value}\\"%\'')

        if not conditions:
            raise ValueError("Brak warunków do usunięcia rekordów")

        where_clause = " AND ".join(conditions)

        try:
            before_count = table.count_rows()
        except Exception:
            before_count = None

        table.delete(where=where_clause)

        after_count = None
        try:
            after_count = table.count_rows()
        except Exception:
            after_count = None

        if before_count is not None and after_count is not None:
            deleted = max(before_count - after_count, 0)
        else:
            deleted = 0

        logger.info(
            "Usuwanie z pamięci (collection=%s) where=%s, usunięto szac. %s rekordów",
            collection_name or self.collection_name,
            where_clause,
            deleted,
        )
        return deleted

    def list_entries(
        self,
        collection_name: Optional[str] = None,
        limit: int = 200,
        metadata_filters: Optional[Dict[str, Any]] = None,
        entry_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Zwraca listę wpisów (id, text, metadata) z bazy dla wizualizacji/diagnostyki.

        Args:
            collection_name: nazwa kolekcji (domyślna, jeśli None)
            limit: maksymalna liczba rekordów
            metadata_filters: słownik klucz→wartość, filtr exact match w metadacie

        Returns:
            Lista słowników z polami: id, text, metadata
        """
        table = self._get_or_create_table(collection_name)

        # Bieżąca wersja LanceDB nie wspiera filtrów/limitów w to_arrow,
        # więc pobieramy pełną tabelę i filtrujemy w Pythonie.
        arrow_table = table.to_arrow()
        rows = arrow_table.to_pylist()
        results: List[Dict[str, Any]] = []
        for row in rows:
            meta_raw = row.get("metadata") or "{}"
            try:
                meta = (
                    json.loads(meta_raw)
                    if isinstance(meta_raw, str)
                    else dict(meta_raw)
                )
            except Exception:
                meta = {}
            if entry_id and row.get("id") != entry_id:
                continue
            if metadata_filters:
                match = True
                for key, val in metadata_filters.items():
                    if val is None:
                        continue
                    if meta.get(key) != val:
                        match = False
                        break
                if not match:
                    continue
            results.append(
                {
                    "id": row.get("id"),
                    "text": row.get("text"),
                    "metadata": meta,
                }
            )
            if limit and len(results) >= limit:
                break
        return results

    def delete_entry(self, entry_id: str, collection_name: Optional[str] = None) -> int:
        """Usuwa pojedynczy rekord po id."""
        if not entry_id:
            return 0

        # Walidacja entry_id: bardzo restrykcyjna
        MAX_ID_LENGTH = 128
        if not isinstance(entry_id, str) or len(entry_id) > MAX_ID_LENGTH:
            raise ValueError(
                f"Nieprawidłowy format entry_id: długość {len(entry_id)} przekracza maksymalną {MAX_ID_LENGTH}"
            )

        # Tylko UUID-like lub bezpieczne identyfikatory (alfanumeryczne + dash + underscore)
        if not re.match(r"^[a-zA-Z0-9\-_]+$", entry_id):
            raise ValueError(f"entry_id zawiera niedozwolone znaki: {entry_id}")

        table = self._get_or_create_table(collection_name)
        # Podwójne escapowanie mimo walidacji (defense in depth)
        safe_id = entry_id.replace("\\", "\\\\").replace("'", "''")
        table.delete(where=f"id = '{safe_id}'")
        return 1

    def delete_session(
        self, session_id: str, collection_name: Optional[str] = None
    ) -> int:
        """
        Usuwa rekordy powiązane z danym session_id (dev/test cleanup).
        """
        if not session_id:
            return 0

        # Walidacja session_id: bardzo restrykcyjna
        MAX_SESSION_ID_LENGTH = 128
        if not isinstance(session_id, str) or len(session_id) > MAX_SESSION_ID_LENGTH:
            raise ValueError(
                f"Nieprawidłowy session_id: długość {len(session_id)} "
                f"przekracza maksymalną {MAX_SESSION_ID_LENGTH}"
            )

        # Tylko bezpieczne identyfikatory (alfanumeryczne + dash + underscore)
        if not re.match(r"^[a-zA-Z0-9\-_]+$", session_id):
            raise ValueError(f"session_id zawiera niedozwolone znaki: {session_id}")

        table = self._get_or_create_table(collection_name)
        # Podwójne escapowanie mimo walidacji (defense in depth)
        safe_id = (
            session_id.replace("\\", "\\\\").replace("'", "''").replace('"', '\\"')
        )
        clause = f'metadata LIKE \'%\\"session_id\\": \\"{safe_id}\\"%\''
        try:
            before = table.count_rows()
        except Exception:
            before = None
        table.delete(where=clause)
        try:
            after = table.count_rows()
        except Exception:
            after = None
        if before is not None and after is not None:
            return max(before - after, 0)
        return 0

    def wipe_collection(self, collection_name: Optional[str] = None) -> int:
        """
        Usuwa wszystkie rekordy z kolekcji (dev/test cleanup).
        """
        table = self._get_or_create_table(collection_name)
        try:
            before = table.count_rows()
        except Exception:
            before = None
        table.delete(where="TRUE")
        try:
            after = table.count_rows()
        except Exception:
            after = None
        if before is not None and after is not None:
            return max(before - after, 0)
        return 0

    def update_metadata(
        self,
        entry_id: str,
        metadata_patch: Dict[str, Any],
        collection_name: Optional[str] = None,
    ) -> bool:
        """
        Aktualizuje metadane rekordu (nadpisuje/uzupełnia), zachowując tekst.
        Implementacja: odczyt -> delete -> upsert z tym samym id.
        """
        if not entry_id:
            return False
        entries = self.list_entries(
            collection_name=collection_name, limit=1, entry_id=entry_id
        )
        if not entries:
            return False
        entry = entries[0]
        text = entry.get("text") or ""
        meta = entry.get("metadata") or {}
        meta.update(metadata_patch or {})
        # usuń stary zapis
        self.delete_entry(entry_id, collection_name=collection_name)
        # wstaw z tym samym id (chunk_text False, aby nie dzielić)
        self.upsert(
            text=text,
            metadata=meta,
            collection_name=collection_name,
            chunk_text=False,
            id_override=entry_id,
        )
        return True
