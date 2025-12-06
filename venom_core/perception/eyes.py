"""Moduł: eyes - warstwa percepcji wizualnej."""

import base64
import os
from pathlib import Path
from typing import Optional

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class Eyes:
    """Warstwa percepcji wizualnej - analiza obrazów."""

    # Nazwy modeli vision do wykrycia w lokalnych modelach
    VISION_MODEL_NAMES = ["llava", "vision", "moondream", "bakllava"]

    def __init__(self):
        """Inicjalizacja Eyes z konfiguracją hybrid (local-first)."""
        self.use_openai = bool(SETTINGS.OPENAI_API_KEY)
        self.local_vision_available = self._check_local_vision()
        self.local_vision_model = None  # Będzie ustawiony jeśli dostępny

        if self.use_openai:
            logger.info("Eyes: Używam OpenAI GPT-4o dla vision")
        elif self.local_vision_available:
            logger.info(f"Eyes: Używam lokalnego modelu vision: {self.local_vision_model}")
        else:
            logger.warning("Eyes: Brak dostępnych modeli vision (ani local, ani cloud)")

    def _check_local_vision(self) -> bool:
        """Sprawdza czy lokalny model vision jest dostępny."""
        # Sprawdź czy Ollama działa i ma model vision
        try:
            import httpx

            response = httpx.get(
                f"{SETTINGS.LLM_LOCAL_ENDPOINT.rstrip('/v1')}/api/tags", timeout=2.0
            )
            if response.status_code == 200:
                models = response.json().get("models", [])
                # Szukaj modeli vision
                for model in models:
                    model_name = model.get("name", "").lower()
                    for vision_name in self.VISION_MODEL_NAMES:
                        if vision_name in model_name:
                            self.local_vision_model = model.get("name")
                            return True
        except Exception as e:
            logger.debug(f"Nie można sprawdzić lokalnych modeli vision: {e}")

        return False

    async def analyze_image(
        self, image_path_or_base64: str, prompt: str = "Co widzisz na tym obrazie?"
    ) -> str:
        """
        Analizuje obraz i zwraca opis.

        Args:
            image_path_or_base64: Ścieżka do pliku lub string base64
            prompt: Pytanie o obraz

        Returns:
            Tekstowy opis tego co jest na obrazie

        Raises:
            ValueError: Jeśli obraz nie może być załadowany
            RuntimeError: Jeśli żaden model vision nie jest dostępny
        """
        logger.info(f"Eyes analizuje obraz z promptem: {prompt[:50]}...")

        # Przygotuj base64
        image_base64 = self._prepare_image_base64(image_path_or_base64)

        # Wybierz strategię
        if self.use_openai:
            return await self._analyze_with_openai(image_base64, prompt)
        elif self.local_vision_available:
            return await self._analyze_with_local(image_base64, prompt)
        else:
            raise RuntimeError(
                "Brak dostępnych modeli vision. Skonfiguruj OPENAI_API_KEY lub uruchom lokalny model vision (np. llava w Ollama)."
            )

    def _prepare_image_base64(self, image_path_or_base64: str) -> str:
        """
        Przygotowuje base64 z obrazu.

        Args:
            image_path_or_base64: Ścieżka lub już gotowy base64

        Returns:
            String base64 bez prefiksu data:image
        """
        # Jeśli to już base64, użyj go
        if image_path_or_base64.startswith("data:image"):
            # Usuń prefix "data:image/png;base64,"
            return image_path_or_base64.split(",", 1)[1]
        elif len(image_path_or_base64) > 500 and "/" not in image_path_or_base64:
            # Prawdopodobnie czysty base64
            return image_path_or_base64

        # W przeciwnym razie to ścieżka do pliku
        file_path = Path(image_path_or_base64)
        if not file_path.exists():
            raise ValueError(f"Plik nie istnieje: {file_path}")

        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def _analyze_with_openai(self, image_base64: str, prompt: str) -> str:
        """Analiza obrazu przez OpenAI GPT-4o."""
        try:
            import httpx

            api_key = SETTINGS.OPENAI_API_KEY
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                },
                            },
                        ],
                    }
                ],
                "max_tokens": 500,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                description = result["choices"][0]["message"]["content"]
                logger.info("OpenAI vision: analiza zakończona")
                return description

        except Exception as e:
            logger.error(f"Błąd podczas analizy przez OpenAI: {e}")
            raise

    async def _analyze_with_local(self, image_base64: str, prompt: str) -> str:
        """Analiza obrazu przez lokalny model (Ollama)."""
        try:
            import httpx

            # Ollama API dla vision
            endpoint = f"{SETTINGS.LLM_LOCAL_ENDPOINT.rstrip('/v1')}/api/generate"

            # Użyj wykrytego modelu lub fallback do llava
            model_name = self.local_vision_model or "llava"

            payload = {
                "model": model_name,
                "prompt": prompt,
                "images": [image_base64],
                "stream": False,
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                result = response.json()
                description = result.get("response", "")
                logger.info(f"Lokalny vision model ({model_name}): analiza zakończona")
                return description

        except Exception as e:
            logger.error(f"Błąd podczas analizy lokalnej: {e}")
            raise
