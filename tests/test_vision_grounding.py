"""Testy jednostkowe dla VisionGrounding."""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from venom_core.perception.vision_grounding import VisionGrounding


class TestVisionGrounding:
    """Testy dla VisionGrounding."""

    @pytest.fixture
    def vision_grounding(self):
        """Fixture do tworzenia VisionGrounding."""
        with patch("venom_core.perception.vision_grounding.SETTINGS") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            vg = VisionGrounding()
            return vg

    @pytest.fixture
    def sample_image(self):
        """Fixture do tworzenia przykładowego obrazu."""
        img = Image.new("RGB", (100, 100), color="red")
        return img

    def test_initialization_no_openai(self, vision_grounding):
        """Test inicjalizacji bez OpenAI."""
        assert vision_grounding.use_openai is False

    def test_initialization_with_openai(self):
        """Test inicjalizacji z OpenAI."""
        with patch("venom_core.perception.vision_grounding.SETTINGS") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key"
            vg = VisionGrounding()
            assert vg.use_openai is True

    @pytest.mark.asyncio
    async def test_locate_element_with_openai(self, sample_image):
        """Test lokalizacji elementu przez OpenAI."""
        with patch("venom_core.perception.vision_grounding.SETTINGS") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key"
            vg = VisionGrounding()

            # Mock odpowiedzi OpenAI
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "450,230"}}]
            }

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                result = await vg.locate_element(sample_image, "red button")

                assert result is not None
                assert result == (450, 230)

    @pytest.mark.asyncio
    async def test_locate_element_openai_not_found(self, sample_image):
        """Test gdy OpenAI nie znalazł elementu."""
        with patch("venom_core.perception.vision_grounding.SETTINGS") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key"
            vg = VisionGrounding()

            # Mock odpowiedzi OpenAI - element nie znaleziony
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "BRAK"}}]
            }

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                result = await vg.locate_element(sample_image, "non-existent button")

                assert result is None

    @pytest.mark.asyncio
    async def test_locate_element_fallback(self, vision_grounding, sample_image):
        """Test fallback lokalizacji (bez OpenAI)."""
        # Bez OpenAI i bez pytesseract - powinien zwrócić None (bezpieczeństwo)
        with patch.dict("sys.modules", {"pytesseract": None}):
            result = vision_grounding._locate_with_fallback(sample_image, "button")

            # Dla bezpieczeństwa fallback zwraca None zamiast środka ekranu
            assert result is None

    @pytest.mark.asyncio
    async def test_locate_element_fallback_with_ocr(
        self, vision_grounding, sample_image
    ):
        """Test fallback lokalizacji z OCR."""
        # Mock pytesseract
        mock_ocr_data = {
            "text": ["", "button", ""],
            "left": [0, 30, 0],
            "top": [0, 40, 0],
            "width": [0, 20, 0],
            "height": [0, 10, 0],
        }

        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_data.return_value = mock_ocr_data
        mock_pytesseract.Output.DICT = "dict"

        with patch.dict("sys.modules", {"pytesseract": mock_pytesseract}):
            # Zaimportuj ponownie metodę z nowym mockiem
            from venom_core.perception.vision_grounding import VisionGrounding

            vg = VisionGrounding()
            result = vg._locate_with_fallback(sample_image, "button")

            assert result is not None
            # Środek znalezionego elementu: left + width/2, top + height/2
            assert result == (40, 45)  # 30 + 20/2, 40 + 10/2

    def test_load_screenshot_from_bytes(self, vision_grounding):
        """Test ładowania zrzutu z bytes."""
        img = Image.new("RGB", (50, 50), color="blue")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_bytes = buffer.getvalue()

        loaded = vision_grounding.load_screenshot(img_bytes)
        assert loaded.size == (50, 50)

    def test_load_screenshot_from_file(self, vision_grounding, tmp_path):
        """Test ładowania zrzutu z pliku."""
        img = Image.new("RGB", (60, 60), color="green")
        img_path = tmp_path / "test.png"
        img.save(img_path)

        loaded = vision_grounding.load_screenshot(str(img_path))
        assert loaded.size == (60, 60)

    def test_load_screenshot_invalid_file(self, vision_grounding):
        """Test ładowania nieistniejącego pliku."""
        with pytest.raises(ValueError):
            vision_grounding.load_screenshot("/nonexistent/path/image.png")

    @pytest.mark.asyncio
    async def test_locate_element_openai_error(self, sample_image):
        """Test obsługi błędu OpenAI API."""
        with patch("venom_core.perception.vision_grounding.SETTINGS") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key"
            vg = VisionGrounding()

            # Mock błędu w zapytaniu
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    side_effect=Exception("API Error")
                )

                result = await vg.locate_element(sample_image, "button")

                assert result is None

    @pytest.mark.asyncio
    async def test_locate_element_with_confidence_threshold(self, sample_image):
        """Test lokalizacji z progiem pewności."""
        with patch("venom_core.perception.vision_grounding.SETTINGS") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key"
            vg = VisionGrounding()

            # Mock odpowiedzi z niską pewnością
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "450,230,0.5"}}]  # Niska pewność
            }

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                # Próg wyższy niż pewność - powinno zwrócić None
                result = await vg.locate_element(
                    sample_image, "button", confidence_threshold=0.7
                )

                assert result is None

    @pytest.mark.asyncio
    async def test_locate_element_with_high_confidence(self, sample_image):
        """Test lokalizacji z wysoką pewnością powyżej progu."""
        with patch("venom_core.perception.vision_grounding.SETTINGS") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key"
            vg = VisionGrounding()

            # Mock odpowiedzi z wysoką pewnością
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "450,230,0.95"}}]  # Wysoka pewność
            }

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                # Próg niższy niż pewność - powinno zwrócić współrzędne
                result = await vg.locate_element(
                    sample_image, "button", confidence_threshold=0.7
                )

                assert result == (450, 230)

    @pytest.mark.asyncio
    async def test_locate_element_without_confidence_in_response(self, sample_image):
        """Test lokalizacji gdy odpowiedź nie zawiera confidence."""
        with patch("venom_core.perception.vision_grounding.SETTINGS") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key"
            vg = VisionGrounding()

            # Mock odpowiedzi bez confidence (stary format)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "450,230"}}]  # Brak confidence
            }

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                # Domyślnie confidence = 1.0, więc powinno przejść
                result = await vg.locate_element(
                    sample_image, "button", confidence_threshold=0.7
                )

                assert result == (450, 230)
