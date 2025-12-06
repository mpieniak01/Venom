"""Moduł: embedding_service - Serwis do generowania embeddingów tekstowych."""

from functools import lru_cache
from typing import List

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


# Cache na poziomie modułu, aby uniknąć problemów z lru_cache na metodach instancji
_embedding_cache = {}


class EmbeddingService:
    """
    Serwis do generowania embeddingów tekstowych.
    Obsługuje tryb lokalny (sentence-transformers) oraz OpenAI API.
    """

    def __init__(self, service_type: str = None):
        """
        Inicjalizacja serwisu embeddingów.

        Args:
            service_type: Typ serwisu ("local" lub "openai"). Domyślnie z SETTINGS.
        """
        self.service_type = service_type or SETTINGS.LLM_SERVICE_TYPE
        self._model = None
        self._client = None
        logger.info(f"EmbeddingService inicjalizowany z typem: {self.service_type}")

    def _ensure_model_loaded(self):
        """Lazy loading modelu embeddingów."""
        if self._model is not None or self._client is not None:
            return

        if self.service_type == "local":
            try:
                from sentence_transformers import SentenceTransformer

                model_name = "sentence-transformers/all-MiniLM-L6-v2"
                logger.info(f"Ładowanie lokalnego modelu embeddingów: {model_name}")
                self._model = SentenceTransformer(model_name)
                logger.info("Model embeddingów załadowany pomyślnie")
            except ImportError:
                logger.error(
                    "sentence-transformers nie jest zainstalowany. Zainstaluj: pip install sentence-transformers"
                )
                raise
        elif self.service_type == "openai":
            try:
                from openai import OpenAI

                if not SETTINGS.OPENAI_API_KEY:
                    raise ValueError(
                        "OPENAI_API_KEY jest wymagany dla service_type='openai'"
                    )

                logger.info("Inicjalizacja klienta OpenAI do embeddingów")
                self._client = OpenAI(api_key=SETTINGS.OPENAI_API_KEY)
                logger.info("Klient OpenAI zainicjalizowany pomyślnie")
            except ImportError:
                logger.error(
                    "openai nie jest zainstalowany. Zainstaluj: pip install openai"
                )
                raise
        else:
            raise ValueError(
                f"Nieznany typ serwisu embeddingów: {self.service_type}. Dostępne: local, openai"
            )

    def _get_embedding_impl(self, text: str) -> List[float]:
        """
        Wewnętrzna implementacja generowania embeddingu (bez cache).

        Args:
            text: Tekst do zakodowania

        Returns:
            Lista floatów reprezentująca embedding
        """
        self._ensure_model_loaded()

        if self.service_type == "local":
            embedding = self._model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        elif self.service_type == "openai":
            response = self._client.embeddings.create(
                model="text-embedding-3-small", input=text
            )
            return response.data[0].embedding

    def get_embedding(self, text: str) -> List[float]:
        """
        Generuje embedding dla podanego tekstu z cache'owaniem.

        Args:
            text: Tekst do zakodowania

        Returns:
            Lista floatów reprezentująca embedding

        Raises:
            ValueError: Jeśli tekst jest pusty
        """
        if not text or not text.strip():
            raise ValueError("Tekst nie może być pusty")

        text_normalized = text.strip()
        cache_key = (self.service_type, text_normalized)
        
        # Sprawdź cache
        if cache_key in _embedding_cache:
            logger.debug(f"Embedding z cache dla tekstu ({len(text)} znaków)")
            return _embedding_cache[cache_key]
        
        # Generuj nowy embedding
        logger.debug(f"Generowanie embeddingu dla tekstu ({len(text)} znaków)")
        embedding = self._get_embedding_impl(text_normalized)
        
        # Zapisz do cache (ogranicz rozmiar cache do 1000 wpisów)
        if len(_embedding_cache) >= 1000:
            # Usuń najstarszy wpis (FIFO)
            _embedding_cache.pop(next(iter(_embedding_cache)))
        _embedding_cache[cache_key] = embedding
        
        return embedding

    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generuje embeddingi dla wielu tekstów (batch processing).

        Args:
            texts: Lista tekstów do zakodowania

        Returns:
            Lista embeddingów

        Raises:
            ValueError: Jeśli lista tekstów jest pusta
        """
        if not texts:
            raise ValueError("Lista tekstów nie może być pusta")

        logger.info(f"Generowanie embeddingów dla {len(texts)} tekstów")

        self._ensure_model_loaded()

        if self.service_type == "local":
            # Batch encoding dla lepszej wydajności
            embeddings = self._model.encode(texts, convert_to_numpy=True)
            return [emb.tolist() for emb in embeddings]
        elif self.service_type == "openai":
            # OpenAI też wspiera batch
            response = self._client.embeddings.create(
                model="text-embedding-3-small", input=texts
            )
            return [item.embedding for item in response.data]

    def clear_cache(self):
        """Czyści cache embeddingów."""
        _embedding_cache.clear()
        logger.info("Cache embeddingów wyczyszczony")

    @property
    def embedding_dimension(self) -> int:
        """
        Zwraca wymiar embeddingu dla używanego modelu.

        Returns:
            Liczba wymiarów embeddingu
        """
        self._ensure_model_loaded()

        if self.service_type == "local":
            # all-MiniLM-L6-v2 ma 384 wymiary
            return self._model.get_sentence_embedding_dimension()
        elif self.service_type == "openai":
            # text-embedding-3-small ma 1536 wymiarów
            return 1536
