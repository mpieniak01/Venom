"""Moduł: media_skill - generowanie i przetwarzanie obrazów."""

import time
from pathlib import Path
from typing import Annotated, Any, Optional

from PIL import Image, ImageDraw, ImageFont
from semantic_kernel.functions import kernel_function

from venom_core.config import SETTINGS
from venom_core.infrastructure.traffic_control import TrafficControlledHttpClient
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class MediaSkill:
    """
    Skill do generowania i przetwarzania obrazów (grafiki, logo, assety).

    Obsługuje:
    - Generowanie obrazów przez OpenAI DALL-E (jeśli skonfigurowano)
    - Fallback: Generowanie placeholderów przez Pillow
    - Zmiana rozmiaru obrazów
    - Przygotowanie assetów web (favicon, og:image)
    """

    def __init__(self, assets_dir: Optional[str] = None):
        """
        Inicjalizacja MediaSkill.

        Args:
            assets_dir: Katalog do zapisu wygenerowanych assetów (domyślnie z SETTINGS)
        """
        self.assets_dir = Path(assets_dir or SETTINGS.ASSETS_DIR)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

        self.service = SETTINGS.IMAGE_GENERATION_SERVICE
        self.default_size = SETTINGS.IMAGE_DEFAULT_SIZE

        # Endpoint dla Stable Diffusion z konfiguracji
        self.sd_endpoint = SETTINGS.STABLE_DIFFUSION_ENDPOINT

        # Sprawdź czy OpenAI jest dostępny
        self.openai_available = False
        self.openai_client: Any = None
        if self.service in ("openai", "hybrid") or SETTINGS.AI_MODE in (
            "HYBRID",
            "CLOUD",
        ):
            try:
                from openai import AsyncOpenAI

                if SETTINGS.OPENAI_API_KEY:
                    self.openai_client = AsyncOpenAI(api_key=SETTINGS.OPENAI_API_KEY)
                    self.openai_available = True
                    logger.info("OpenAI DALL-E dostępny dla generowania obrazów")
                else:
                    logger.warning(
                        "IMAGE_GENERATION_SERVICE=openai, ale brak OPENAI_API_KEY. "
                        "Używam fallback (placeholder)"
                    )
            except ImportError:
                logger.warning("Biblioteka openai niedostępna. Używam fallback.")

        logger.info(
            f"MediaSkill zainicjalizowany (service={self.service}, "
            f"assets_dir={self.assets_dir})"
        )

    @kernel_function(
        name="generate_image",
        description="Generuje obraz na podstawie promptu tekstowego",
    )
    async def generate_image(
        self,
        prompt: Annotated[str, "Prompt opisujący obraz do wygenerowania"],
        size: Annotated[
            str, "Rozmiar obrazu, np. '1024x1024', '512x512'"
        ] = "1024x1024",
        style: Annotated[
            str, "Styl obrazu: 'vivid' (żywy) lub 'natural' (naturalny)"
        ] = "vivid",
        filename: Annotated[str, "Nazwa pliku (opcjonalnie)"] = "",
    ) -> str:
        """
        Generuje obraz i zapisuje w katalogu assets.

        Args:
            prompt: Opis obrazu (np. "Minimalist logo for fintech app")
            size: Rozmiar obrazu
            style: Styl obrazu (dla DALL-E)
            filename: Opcjonalna nazwa pliku (domyślnie: timestamp)

        Returns:
            Ścieżka do wygenerowanego obrazu
        """
        logger.info(f"Generowanie obrazu: '{prompt[:50]}...'")

        # Krok 1: Spróbuj lokalny Stable Diffusion (Local First)
        if self.service in ("local-sd", "placeholder"):
            # Sprawdź czy lokalne API działa
            sd_result = await self._generate_with_stable_diffusion(
                prompt, size, filename
            )
            if sd_result:
                return sd_result

        # Krok 2: Fallback do DALL-E (jeśli dostępny i tryb HYBRID/CLOUD)
        if (
            self.service in ("openai", "hybrid")
            or SETTINGS.AI_MODE in ("HYBRID", "CLOUD")
        ) and self.openai_available:
            dalle_result = await self._generate_with_dalle(
                prompt, size, style, filename
            )
            if dalle_result:
                return dalle_result

        # Krok 3: Emergency fallback - Placeholder z Pillow
        logger.info("Wszystkie AI engines niedostępne, używam Pillow placeholder")
        return self._generate_placeholder(prompt, size, filename)

    async def _generate_with_stable_diffusion(
        self, prompt: str, size: str, filename: str
    ) -> Optional[str]:
        """
        Generuje obraz przez lokalne API Stable Diffusion (Automatic1111).

        Args:
            prompt: Prompt tekstowy
            size: Rozmiar obrazu (np. "1024x1024")
            filename: Nazwa pliku

        Returns:
            Ścieżka do wygenerowanego obrazu lub None jeśli API niedostępne
        """
        try:
            import base64

            # Parse rozmiaru
            try:
                width, height = map(int, size.lower().split("x"))
            except ValueError:
                logger.warning(
                    f"Nieprawidłowy format rozmiaru: {size}. Używam 1024x1024"
                )
                width, height = 1024, 1024

            # Sprawdź dostępność API
            logger.info(f"Próba połączenia z Stable Diffusion API: {self.sd_endpoint}")

            async with TrafficControlledHttpClient(
                provider="stable_diffusion",
                timeout=SETTINGS.SD_PING_TIMEOUT,
            ) as client:
                # Ping endpoint
                try:
                    ping_response = await client.aget(
                        f"{self.sd_endpoint}/sdapi/v1/",
                        raise_for_status=False,
                    )
                    if ping_response.status_code != 200:
                        logger.warning(
                            f"Stable Diffusion API nie odpowiada (status {ping_response.status_code})"
                        )
                        return None
                except Exception as e:
                    logger.info(f"Stable Diffusion API niedostępny: {e}")
                    return None

            # API dostępne - generuj obraz
            logger.info("Stable Diffusion API dostępny, generuję obraz...")

            payload = {
                "prompt": prompt,
                "negative_prompt": "blurry, bad quality, distorted, ugly",
                "steps": SETTINGS.SD_DEFAULT_STEPS,
                "width": width,
                "height": height,
                "cfg_scale": SETTINGS.SD_DEFAULT_CFG_SCALE,
                "sampler_name": SETTINGS.SD_DEFAULT_SAMPLER,
            }

            async with TrafficControlledHttpClient(
                provider="stable_diffusion",
                timeout=SETTINGS.SD_GENERATION_TIMEOUT,
            ) as client:
                response = await client.apost(
                    f"{self.sd_endpoint}/sdapi/v1/txt2img",
                    json=payload,
                )

            result = response.json()
            if not result.get("images"):
                logger.error("Stable Diffusion nie zwrócił obrazów")
                return None

            # Zdekoduj base64
            image_data = base64.b64decode(result["images"][0])

            # Zapisz obraz
            if not filename:
                filename = f"sd_{int(time.time())}.png"
            if not filename.endswith(".png"):
                filename += ".png"

            output_path = self.assets_dir / filename
            output_path.write_bytes(image_data)

            logger.info(f"✓ Obraz wygenerowany przez Stable Diffusion: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.warning(f"Błąd podczas generowania przez Stable Diffusion: {e}")
            return None

    async def _generate_with_dalle(
        self, prompt: str, size: str, style: str, filename: str
    ) -> Optional[str]:
        """
        Generuje obraz przez OpenAI DALL-E.

        Args:
            prompt: Prompt tekstowy
            size: Rozmiar obrazu
            style: Styl obrazu
            filename: Nazwa pliku

        Returns:
            Ścieżka do wygenerowanego obrazu
        """
        try:
            # DALL-E 3 wspiera tylko 1024x1024, 1024x1792, 1792x1024
            valid_sizes = ["1024x1024", "1024x1792", "1792x1024"]
            if size not in valid_sizes:
                logger.warning(
                    f"Rozmiar {size} nie jest wspierany przez DALL-E 3. Używam 1024x1024"
                )
                size = "1024x1024"

            response = await self.openai_client.images.generate(
                model=SETTINGS.DALLE_MODEL,
                prompt=prompt,
                size=size,
                style=style,
                n=1,
            )

            image_url = response.data[0].url

            # Pobierz obraz
            async with TrafficControlledHttpClient(
                provider="openai_images",
                timeout=30.0,
            ) as client:
                img_response = await client.aget(image_url)

            # Zapisz obraz
            if not filename:
                filename = f"dalle_{int(time.time())}.png"
            if not filename.endswith(".png"):
                filename += ".png"

            output_path = self.assets_dir / filename
            output_path.write_bytes(img_response.content)

            logger.info(f"✓ Obraz wygenerowany przez DALL-E: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Błąd podczas generowania przez DALL-E: {e}")
            return None

    def _generate_placeholder(self, prompt: str, size: str, filename: str) -> str:
        """
        Generuje placeholder obrazu używając Pillow (fallback).

        Args:
            prompt: Tekst do wstawienia na obrazie
            size: Rozmiar obrazu
            filename: Nazwa pliku

        Returns:
            Ścieżka do wygenerowanego placeholdera
        """
        logger.info("Generowanie placeholdera obrazu...")

        # Parse size
        try:
            w, h = map(int, size.lower().split("x"))
        except ValueError:
            logger.warning(f"Nieprawidłowy format rozmiaru: {size}. Używam 1024x1024")
            w, h = 1024, 1024

        # Stwórz obraz
        img = Image.new("RGB", (w, h), color="#1e1e1e")
        draw = ImageDraw.Draw(img)

        # Dodaj tekst
        font: Any = ImageFont.load_default()
        try:
            # Spróbuj użyć domyślnej czcionki
            font_size = min(w, h) // 20
            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size
                )
            except (OSError, IOError):
                font = ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()

        # Dodaj tekst na środku
        text = prompt[:50] if len(prompt) > 50 else prompt

        # Oblicz pozycję tekstu (wycentrowany)
        # Używamy textbbox dla kompatybilności z nowszymi wersjami Pillow
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (w - text_width) // 2
        y = (h - text_height) // 2

        # Rysuj tło pod tekstem
        padding = 20
        draw.rectangle(
            [
                x - padding,
                y - padding,
                x + text_width + padding,
                y + text_height + padding,
            ],
            fill="#2d2d2d",
        )

        # Rysuj tekst
        draw.text((x, y), text, fill="#ffffff", font=font)

        # Zapisz obraz
        if not filename:
            filename = f"placeholder_{int(time.time())}.png"
        if not filename.endswith(".png"):
            filename += ".png"

        output_path = self.assets_dir / filename
        img.save(output_path, "PNG")

        logger.info(f"✓ Placeholder wygenerowany: {output_path}")
        return str(output_path)

    @kernel_function(
        name="resize_image",
        description="Zmienia rozmiar obrazu (przygotowanie assetów web)",
    )
    async def resize_image(
        self,
        image_path: Annotated[str, "Ścieżka do obrazu źródłowego"],
        width: Annotated[int, "Docelowa szerokość"],
        height: Annotated[int, "Docelowa wysokość"],
        output_name: Annotated[str, "Nazwa pliku wyjściowego (opcjonalnie)"] = "",
    ) -> str:
        """
        Zmienia rozmiar obrazu.

        Args:
            image_path: Ścieżka do obrazu źródłowego
            width: Nowa szerokość
            height: Nowa wysokość
            output_name: Opcjonalna nazwa pliku wyjściowego

        Returns:
            Ścieżka do przetworzonego obrazu
        """
        logger.info(f"Zmiana rozmiaru obrazu: {image_path} -> {width}x{height}")

        try:
            img_path = Path(image_path)
            if not img_path.exists():
                raise FileNotFoundError(f"Obraz nie istnieje: {image_path}")

            # Wczytaj obraz
            img = Image.open(img_path)

            # Zmień rozmiar (LANCZOS dla najlepszej jakości)
            resized = img.resize((width, height), Image.Resampling.LANCZOS)

            # Zapisz
            if not output_name:
                output_name = f"{img_path.stem}_{width}x{height}{img_path.suffix}"

            output_path = self.assets_dir / output_name
            resized.save(output_path)

            logger.info(f"✓ Obraz zmieniony: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Błąd podczas zmiany rozmiaru: {e}")
            raise

    @kernel_function(
        name="list_assets",
        description="Wyświetla listę wygenerowanych assetów",
    )
    async def list_assets(self) -> str:
        """
        Wyświetla listę wszystkich wygenerowanych assetów.

        Returns:
            Lista plików w katalogu assets
        """
        try:
            assets = list(self.assets_dir.glob("*"))
            if not assets:
                return "Brak wygenerowanych assetów"

            result = f"Assety w {self.assets_dir}:\n"
            for asset in sorted(assets):
                if asset.is_file():
                    size_kb = asset.stat().st_size / 1024
                    result += f"- {asset.name} ({size_kb:.1f} KB)\n"

            return result

        except Exception as e:
            logger.error(f"Błąd podczas listowania assetów: {e}")
            return f"Błąd: {e}"
