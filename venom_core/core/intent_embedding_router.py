"""Moduł: intent_embedding_router - klasyfikacja intencji przy użyciu embeddingów.

Ten moduł implementuje lekki, szybki etap klasyfikacji intencji oparty o embeddingi,
który działa jako dodatkowa warstwa przed klasyfikacją LLM w IntentManager.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class IntentEmbeddingRouter:
    """Router intencji oparty na embeddingach zdań.

    Wykorzystuje lekki model sentence-transformers do klasyfikacji intencji
    przed przejściem do droższej klasyfikacji LLM.
    """

    def __init__(
        self,
        lexicon_dir: Path,
        model_name: Optional[str] = None,
        min_score: Optional[float] = None,
        margin: Optional[float] = None,
    ):
        """Inicjalizuje router embeddingów intencji.

        Args:
            lexicon_dir: Katalog z plikami lexicon intent
            model_name: Nazwa modelu sentence-transformers (domyślnie z config)
            min_score: Minimalny próg podobieństwa (domyślnie z config)
            margin: Minimalny margines między top1 a top2 (domyślnie z config)
        """
        self.lexicon_dir = lexicon_dir
        self.model_name = model_name or SETTINGS.INTENT_EMBED_MODEL_NAME
        self.min_score = (
            min_score if min_score is not None else SETTINGS.INTENT_EMBED_MIN_SCORE
        )
        self.margin = margin if margin is not None else SETTINGS.INTENT_EMBED_MARGIN

        self.model = None
        self.intent_embeddings: Dict[str, np.ndarray] = {}
        self.intent_phrases: Dict[str, List[str]] = {}
        self._initialized = False

        # Próba inicjalizacji - jeśli się nie uda, router będzie wyłączony
        try:
            self._initialize()
        except Exception as exc:
            logger.warning(
                "Nie udało się zainicjalizować IntentEmbeddingRouter: %s. "
                "Router będzie wyłączony (graceful fallback).",
                exc,
            )
            self._initialized = False
            # Wyczyść zasoby aby uniknąć trzymania ciężkich obiektów w pamięci
            self.model = None
            self.intent_embeddings = {}
            self.intent_phrases = {}

    def _initialize(self) -> None:
        """Inicjalizuje model i buduje cache embeddingów intencji."""
        if not SETTINGS.ENABLE_INTENT_EMBEDDING_ROUTER:
            logger.info("Intent Embedding Router wyłączony przez feature flag")
            return

        try:
            # Lazy import - nie chcemy blokować startu jeśli biblioteki nie ma
            from sentence_transformers import (
                SentenceTransformer,  # type: ignore[import-not-found]
            )

            logger.info("Ładowanie modelu embeddingów: %s", self.model_name)
            self.model = SentenceTransformer(self.model_name)

            # Załaduj frazy z lexiconów i zbuduj embeddingi
            self._load_intent_phrases()
            self._build_intent_embeddings()

            self._initialized = True
            logger.info(
                "IntentEmbeddingRouter zainicjalizowany dla %d intencji",
                len(self.intent_embeddings),
            )
        except ImportError as exc:
            logger.warning(
                "Brak biblioteki sentence-transformers: %s. "
                "Intent Embedding Router niedostępny.",
                exc,
            )
            raise
        except Exception as exc:
            logger.error(
                "Błąd inicjalizacji Intent Embedding Router: %s", exc, exc_info=True
            )
            raise

    def _load_intent_phrases(self) -> None:
        """Ładuje frazy wzorcowe dla każdej intencji z plików lexicon."""
        # Obsługa wielu języków - łączymy wszystkie frazy
        lexicon_files = [
            "intent_lexicon_en.json",
            "intent_lexicon_pl.json",
            "intent_lexicon_de.json",
        ]

        for filename in lexicon_files:
            file_path = self.lexicon_dir / filename
            if not file_path.exists():
                logger.debug("Plik lexicon nie istnieje: %s", file_path)
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                intents = data.get("intents", {})
                for intent_name, intent_data in intents.items():
                    phrases = intent_data.get("phrases", [])
                    if phrases:
                        if intent_name not in self.intent_phrases:
                            self.intent_phrases[intent_name] = []
                        self.intent_phrases[intent_name].extend(phrases)

            except Exception as exc:
                logger.warning("Błąd ładowania lexicon %s: %s", filename, exc)

        logger.debug(
            "Załadowano frazy dla intencji: %s", list(self.intent_phrases.keys())
        )

    def _build_intent_embeddings(self) -> None:
        """Buduje embeddingi centroidów dla każdej intencji."""
        if not self.model:
            return

        for intent_name, phrases in self.intent_phrases.items():
            if not phrases:
                continue

            try:
                # Oblicz embeddingi dla wszystkich fraz danej intencji
                phrase_embeddings = self.model.encode(
                    phrases, convert_to_numpy=True, show_progress_bar=False
                )

                # Centroid = średnia embeddingów fraz
                centroid = np.mean(phrase_embeddings, axis=0)
                self.intent_embeddings[intent_name] = centroid

            except Exception as exc:
                logger.warning(
                    "Błąd tworzenia embeddingu dla intencji %s: %s", intent_name, exc
                )

    async def classify(
        self, user_input: str
    ) -> Tuple[Optional[str], float, List[Tuple[str, float]]]:
        """Klasyfikuje intencję na podstawie podobieństwa embeddingów.

        Args:
            user_input: Tekst wejściowy użytkownika

        Returns:
            Tuple zawierający:
            - intent: Nazwa intencji lub None jeśli nie spełnia progów
            - score: Najwyższy wynik podobieństwa
            - top2: Lista (intent, score) dla dwóch najlepszych dopasowań
        """
        # Jeśli router nie jest zainicjalizowany, zwróć None (fallback)
        if not self._initialized or not self.model:
            return None, 0.0, []

        try:
            # Import anyio for thread pool execution
            from anyio import to_thread

            # Oblicz embedding dla wejścia w thread pool aby nie blokować event loop
            input_embedding = await to_thread.run_sync(
                lambda: self.model.encode(
                    [user_input], convert_to_numpy=True, show_progress_bar=False
                )[0]
            )

            # Oblicz podobieństwo cosinusowe z każdym centroidem intencji
            similarities = []
            for intent_name, intent_embedding in self.intent_embeddings.items():
                similarity = self._cosine_similarity(input_embedding, intent_embedding)
                similarities.append((intent_name, float(similarity)))

            # Sortuj po podobieństwie malejąco
            similarities.sort(key=lambda x: x[1], reverse=True)

            if not similarities:
                return None, 0.0, []

            top1_intent, top1_score = similarities[0]
            top2 = similarities[:2]

            # Sprawdź progi
            if top1_score < self.min_score:
                logger.debug(
                    "Wynik embedding %.3f poniżej progu %.3f dla '%s'",
                    top1_score,
                    self.min_score,
                    top1_intent,
                )
                return None, top1_score, top2

            # Sprawdź margines między top1 a top2
            if len(similarities) >= 2:
                top2_score = similarities[1][1]
                margin = top1_score - top2_score

                if margin < self.margin:
                    logger.debug(
                        "Margines %.3f poniżej wymaganego %.3f (top1: %s=%.3f, top2: %s=%.3f)",
                        margin,
                        self.margin,
                        top1_intent,
                        top1_score,
                        similarities[1][0],
                        top2_score,
                    )
                    return None, top1_score, top2

            logger.info(
                "Intent Embedding Router: %s (score=%.3f, margin=%.3f)",
                top1_intent,
                top1_score,
                top1_score - (similarities[1][1] if len(similarities) >= 2 else 0.0),
            )

            return top1_intent, top1_score, top2

        except Exception as exc:
            logger.warning(
                "Błąd klasyfikacji embeddingowej: %s. Fallback do następnej warstwy.",
                exc,
            )
            return None, 0.0, []

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Oblicza podobieństwo cosinusowe między dwoma wektorami.

        Args:
            a: Pierwszy wektor
            b: Drugi wektor

        Returns:
            Podobieństwo cosinusowe w zakresie [-1, 1]
        """
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def is_enabled(self) -> bool:
        """Sprawdza czy router jest włączony i gotowy do użycia.

        Returns:
            True jeśli router jest zainicjalizowany i gotowy
        """
        return self._initialized and self.model is not None
