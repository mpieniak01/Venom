"""Moduł: embedding_service - Serwis do generowania embeddingów tekstowych."""

import hashlib
from functools import lru_cache
from typing import Any, List, Optional

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
LOCAL_EMBEDDING_DIMENSION = 384


class EmbeddingService:
    """
    Serwis do generowania embeddingów tekstowych.
    Obsługuje tryb lokalny (sentence-transformers) oraz OpenAI API.
    """

    def __init__(self, service_type: Optional[str] = None):
        """
        Inicjalizacja serwisu embeddingów.

        Args:
            service_type: Typ serwisu ("local" lub "openai"). Domyślnie z SETTINGS.
        """
        self.service_type = service_type or SETTINGS.LLM_SERVICE_TYPE
        if service_type is None and (
            SETTINGS.FORCE_LOCAL_MODEL or SETTINGS.AI_MODE == "LOCAL"
        ):
            self.service_type = "local"
        self._model: Optional[Any] = None
        self._client: Optional[Any] = None
        self._local_fallback_mode = False
        logger.info(f"EmbeddingService inicjalizowany z typem: {self.service_type}")
        # Zachowaj kompatybilność z testami: expose cached getter z cache_info/cache_clear.
        self._get_embedding_cached = lru_cache(maxsize=1000)(
            self._get_embedding_impl_wrapper
        )

    def _ensure_model_loaded(self) -> None:
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
            except Exception as exc:
                logger.warning(
                    "Nie udało się załadować lokalnego modelu embeddingów (%s). "
                    "Przechodzę na fallback deterministyczny 384-dim.",
                    exc,
                )
                self._local_fallback_mode = True
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
            if self._local_fallback_mode:
                return self._generate_fallback_embedding(text)
            if self._model is None:
                raise RuntimeError("Model embeddingów nie został załadowany")
            embedding = self._model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        elif self.service_type == "openai":
            if self._client is None:
                raise RuntimeError("Klient OpenAI nie został zainicjalizowany")
            response = self._client.embeddings.create(
                model="text-embedding-3-small", input=text
            )
            return response.data[0].embedding
        else:  # pragma: no cover - nieobsługiwane typy
            raise ValueError(f"Nieobsługiwany typ serwisu: {self.service_type}")

    def _get_embedding_impl_wrapper(self, text: str) -> List[float]:
        """Opakowanie funkcji z cache LRU (kompatybilne z testami)."""
        return self._get_embedding_impl(text)

    @staticmethod
    def _generate_fallback_embedding(text: str) -> List[float]:
        """
        Generuje deterministyczny embedding 384-dim bez zależności od sieci/modelu.
        """
        values: List[float] = []
        seed = text.encode("utf-8")
        counter = 0
        while len(values) < LOCAL_EMBEDDING_DIMENSION:
            block = hashlib.sha256(seed + counter.to_bytes(4, "little")).digest()
            counter += 1
            for byte in block:
                values.append((byte / 127.5) - 1.0)
                if len(values) == LOCAL_EMBEDDING_DIMENSION:
                    break
        return values

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

        logger.debug(f"Generowanie embeddingu dla tekstu ({len(text)} znaków)")
        return self._get_embedding_cached(text_normalized)

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
            if self._local_fallback_mode:
                return [self._generate_fallback_embedding(text) for text in texts]
            if self._model is None:
                raise RuntimeError("Model embeddingów nie został załadowany")
            # Batch encoding dla lepszej wydajności
            embeddings = self._model.encode(texts, convert_to_numpy=True)
            return [emb.tolist() for emb in embeddings]
        elif self.service_type == "openai":
            if self._client is None:
                raise RuntimeError("Klient OpenAI nie został zainicjalizowany")
            # OpenAI też wspiera batch
            response = self._client.embeddings.create(
                model="text-embedding-3-small", input=texts
            )
            return [item.embedding for item in response.data]
        else:  # pragma: no cover - nieobsługiwane typy
            raise ValueError(f"Nieobsługiwany typ serwisu: {self.service_type}")

    def clear_cache(self):
        """Czyści cache embeddingów."""
        self._get_embedding_cached.cache_clear()
        logger.info("Cache embeddingów wyczyszczony")

    @property
    def embedding_dimension(self) -> int:
        """
        Zwraca wymiar embeddingu dla używanego modelu.

        Returns:
            Liczba wymiarów embeddingu
        """
        if self.service_type == "local":
            # all-MiniLM-L6-v2 ma stały wymiar 384.
            # Zwracamy go bez ładowania modelu, aby uniknąć zależności od sieci.
            if self._model is None:
                return LOCAL_EMBEDDING_DIMENSION
            return self._model.get_sentence_embedding_dimension()
        elif self.service_type == "openai":
            # text-embedding-3-small ma 1536 wymiarów
            return 1536
        self._ensure_model_loaded()
        raise ValueError(f"Nieobsługiwany typ serwisu: {self.service_type}")
