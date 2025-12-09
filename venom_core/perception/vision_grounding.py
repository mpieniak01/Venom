"""
Moduł: vision_grounding - Lokalizacja elementów UI na podstawie opisów wizualnych.

Ten moduł pozwala na znalezienie współrzędnych elementów interfejsu
na podstawie opisów tekstowych lub wizualnych (np. "czerwony przycisk Play").
"""

import base64
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

import httpx
from PIL import Image

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class VisionGrounding:
    """
    Warstwa Vision Grounding - lokalizacja elementów UI.

    Obsługuje:
    - Znajdowanie elementów na podstawie opisu tekstowego
    - Zwracanie współrzędnych (x, y) środka elementu
    - Fallback do prostszych metod gdy zaawansowane modele niedostępne
    """

    def __init__(self):
        """Inicjalizacja VisionGrounding."""
        self.use_openai = bool(SETTINGS.OPENAI_API_KEY)
        logger.info(f"VisionGrounding zainicjalizowany (OpenAI: {self.use_openai})")

    async def locate_element(
        self,
        screenshot: Image.Image,
        description: str,
        confidence_threshold: float = 0.7,
    ) -> Optional[Tuple[int, int]]:
        """
        Lokalizuje element na zrzucie ekranu na podstawie opisu.

        Args:
            screenshot: Obiekt PIL Image ze zrzutem ekranu
            description: Opis elementu do znalezienia (np. "zielony przycisk Zapisz")
            confidence_threshold: Minimalny próg pewności (0.0-1.0)

        Returns:
            Tuple (x, y) ze współrzędnymi środka elementu lub None jeśli nie znaleziono

        Raises:
            RuntimeError: Jeśli żaden model vision nie jest dostępny
        """
        logger.info(f"Lokalizacja elementu: '{description}'")

        if self.use_openai:
            return await self._locate_with_openai(
                screenshot, description, confidence_threshold
            )
        else:
            # Fallback do prostej metody OCR + heurystyki
            logger.warning(
                "Brak zaawansowanego modelu vision. Używam fallback (OCR + heurystyka)"
            )
            return await self._locate_with_fallback(screenshot, description)

    async def _locate_with_openai(
        self,
        screenshot: Image.Image,
        description: str,
        confidence_threshold: float,
    ) -> Optional[Tuple[int, int]]:
        """
        Lokalizuje element używając OpenAI GPT-4o Vision.

        GPT-4o może analizować obraz i zwracać przybliżone współrzędne.

        Args:
            screenshot: Obraz PIL ze zrzutem ekranu
            description: Opis elementu do znalezienia
            confidence_threshold: Próg pewności (0.0-1.0) - wyniki poniżej progu są odrzucane
        """
        try:
            # Konwertuj PIL Image do base64
            buffered = BytesIO()
            screenshot.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

            # Przygotuj prompt
            width, height = screenshot.size
            prompt = f"""Analizujesz zrzut ekranu ({width}x{height} pikseli).

Znajdź element opisany jako: "{description}"

Jeśli element istnieje i jesteś pewien lokalizacji (confidence >= {confidence_threshold}), zwróć współrzędne środka elementu i poziom pewności w formacie: X,Y,CONFIDENCE
Jeśli elementu nie ma lub pewność jest za niska, zwróć: BRAK

Przykład odpowiedzi:
- Jeśli znaleziono z wysoką pewnością: 450,230,0.95
- Jeśli nie znaleziono lub niska pewność: BRAK"""

            # Wywołaj OpenAI API
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
                                    "url": f"data:image/png;base64,{img_base64}",
                                    "detail": "high",
                                },
                            },
                        ],
                    }
                ],
                "max_tokens": 100,
                "temperature": 0.1,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                answer = result["choices"][0]["message"]["content"].strip()

                logger.debug(f"OpenAI Vision odpowiedź: {answer}")

                # Parsuj odpowiedź
                if answer.upper() == "BRAK" or "brak" in answer.lower():
                    logger.info(f"Element '{description}' nie został znaleziony")
                    return None

                # Spróbuj wyciągnąć współrzędne i confidence
                try:
                    parts = answer.replace(" ", "").split(",")
                    if len(parts) >= 2:
                        x = int(parts[0])
                        y = int(parts[1])

                        # Sprawdź czy jest confidence w odpowiedzi
                        confidence = 1.0  # Domyślna wartość jeśli brak
                        if len(parts) >= 3:
                            try:
                                confidence = float(parts[2])
                            except ValueError:
                                logger.warning(
                                    f"Nie można sparsować confidence: {parts[2]}"
                                )

                        # Filtruj wyniki poniżej progu confidence
                        if confidence < confidence_threshold:
                            logger.info(
                                f"Element '{description}' znaleziony ale poniżej progu pewności: {confidence} < {confidence_threshold}"
                            )
                            return None

                        logger.info(
                            f"Element '{description}' znaleziony: ({x}, {y}) z pewnością {confidence}"
                        )
                        return (x, y)
                except (ValueError, IndexError):
                    logger.warning(f"Nie można sparsować współrzędnych: {answer}")
                    return None

        except Exception as e:
            logger.error(f"Błąd podczas lokalizacji przez OpenAI: {e}")
            return None

        return None

    async def _locate_with_fallback(
        self, screenshot: Image.Image, description: str
    ) -> Optional[Tuple[int, int]]:
        """
        Fallback metoda lokalizacji (prosty OCR + heurystyka).

        To jest uproszczona implementacja. W przyszłości może być zastąpiona
        przez lokalny model Florence-2 lub podobny.
        """
        try:
            # Fallback: próbujemy znaleźć element przez OCR, w razie niepowodzenia zwracamy None

            # Bardzo prosty fallback: szukamy tekstu przez pytesseract (jeśli dostępny)
            try:
                import pytesseract

                # OCR na obrazie
                ocr_data = pytesseract.image_to_data(
                    screenshot, output_type=pytesseract.Output.DICT
                )

                # Szukaj słów z opisu w OCR
                description_words = description.lower().split()
                for i, text in enumerate(ocr_data["text"]):
                    if text and any(word in text.lower() for word in description_words):
                        x = ocr_data["left"][i] + ocr_data["width"][i] // 2
                        y = ocr_data["top"][i] + ocr_data["height"][i] // 2
                        logger.info(
                            f"Element '{description}' znaleziony przez OCR: ({x}, {y})"
                        )
                        return (x, y)

                logger.warning(f"OCR nie znalazł elementu: {description}")
                return None

            except ImportError:
                logger.warning("pytesseract nie jest zainstalowany - brak lokalizacji")
                # BEZPIECZEŃSTWO: NIE zwracamy środka ekranu bo może to być
                # niebezpieczny element (np. przycisk "Delete"). Lepiej zwrócić None.
                return None

        except Exception as e:
            logger.error(f"Błąd w fallback lokalizacji: {e}")
            return None

    def load_screenshot(self, path_or_bytes) -> Image.Image:
        """
        Ładuje zrzut ekranu z pliku lub bytes.

        Args:
            path_or_bytes: Ścieżka do pliku lub bytes

        Returns:
            PIL Image

        Raises:
            ValueError: Jeśli nie można załadować obrazu
        """
        try:
            if isinstance(path_or_bytes, bytes):
                return Image.open(BytesIO(path_or_bytes))
            else:
                path = Path(path_or_bytes)
                if not path.exists():
                    raise ValueError(f"Plik nie istnieje: {path}")
                return Image.open(path)
        except Exception as e:
            raise ValueError(f"Nie można załadować obrazu: {e}")
