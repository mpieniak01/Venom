"""Moduł: eyes - warstwa percepcji wizualnej."""

import base64
from pathlib import Path

import httpx

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Stała do rozróżnienia base64 od ścieżki pliku
MIN_BASE64_LENGTH = 500


class Eyes:
    """Warstwa percepcji wizualnej - analiza obrazów."""

    def __init__(self):
        """Inicjalizacja Eyes z konfiguracją hybrid (local-first)."""
        self.use_openai = bool(SETTINGS.OPENAI_API_KEY)
        self.local_vision_available = self._check_local_vision()
        self.local_vision_model = None  # Będzie ustawiony jeśli dostępny

        if self.use_openai:
            logger.info("Eyes: Używam OpenAI GPT-4o dla vision")
        elif self.local_vision_available:
            logger.info(
                f"Eyes: Używam lokalnego modelu vision: {self.local_vision_model}"
            )
        else:
            logger.warning("Eyes: Brak dostępnych modeli vision (ani local, ani cloud)")

    def _check_local_vision(self) -> bool:
        """Sprawdza czy lokalny model vision jest dostępny."""
        # Sprawdź czy Ollama działa i ma model vision
        try:
            response = httpx.get(
                f"{SETTINGS.LLM_LOCAL_ENDPOINT.rstrip('/v1')}/api/tags",
                timeout=SETTINGS.OLLAMA_CHECK_TIMEOUT,
            )
            if response.status_code == 200:
                models = response.json().get("models", [])
                # Szukaj modeli vision
                for model in models:
                    model_name = model.get("name", "").lower()
                    for vision_name in SETTINGS.VISION_MODEL_NAMES:
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

        # Wybierz strategię (local-first dla prywatności)
        if self.local_vision_available:
            return await self._analyze_with_local(image_base64, prompt)
        elif self.use_openai:
            return await self._analyze_with_openai(image_base64, prompt)
        else:
            # Bezpieczne łączenie nazw modeli (obsługa przypadku gdy lista zawiera non-stringi)
            model_names_str = ', '.join(str(name) for name in SETTINGS.VISION_MODEL_NAMES)
            raise RuntimeError(
                f"Brak dostępnych modeli vision. Skonfiguruj OPENAI_API_KEY lub uruchom lokalny model vision (np. {model_names_str} w Ollama)."
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
        elif (
            len(image_path_or_base64) > SETTINGS.MIN_BASE64_LENGTH
            and "/" not in image_path_or_base64
        ):
            # Prawdopodobnie czysty base64 (długi string bez slashów)
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
            api_key = SETTINGS.OPENAI_API_KEY
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            # Określ format MIME na podstawie pierwszych bajtów base64
            # Prosta heurystyka: sprawdź sygnaturę pliku
            mime_type = "image/jpeg"  # domyślny
            try:
                # Dekoduj pierwsze bajty aby sprawdzić sygnaturę
                first_bytes = base64.b64decode(image_base64[:20])
                if first_bytes.startswith(b"\x89PNG"):
                    mime_type = "image/png"
                elif first_bytes.startswith(b"GIF"):
                    mime_type = "image/gif"
                elif first_bytes.startswith(b"RIFF") and b"WEBP" in first_bytes:
                    mime_type = "image/webp"
            except Exception:
                pass  # Użyj domyślnego

            payload = {
                "model": SETTINGS.OPENAI_GPT4O_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_base64}"
                                },
                            },
                        ],
                    }
                ],
                "max_tokens": SETTINGS.VISION_MAX_TOKENS,
            }

            async with httpx.AsyncClient(timeout=SETTINGS.OPENAI_API_TIMEOUT) as client:
                response = await client.post(
                    SETTINGS.OPENAI_CHAT_COMPLETIONS_ENDPOINT,
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

            async with httpx.AsyncClient(timeout=SETTINGS.LOCAL_VISION_TIMEOUT) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                result = response.json()
                description = result.get("response", "")
                logger.info(f"Lokalny vision model ({model_name}): analiza zakończona")
                return description

        except Exception as e:
            logger.error(f"Błąd podczas analizy lokalnej: {e}")
            raise
