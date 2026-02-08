"""Moduł: ingestion_engine - Silnik Ingestii Wieloformatowych Danych."""

import asyncio
import mimetypes
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Stałe dla chunkingu semantycznego
SEMANTIC_CHUNK_SIZE = 1000  # Większe chunki dla semantic splitting
SEMANTIC_OVERLAP = 100
SEMANTIC_SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " "]


def _create_temp_wav_file() -> str:
    """Tworzy pusty plik tymczasowy WAV i zwraca ścieżkę."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        return tmp.name


def _extract_audio_with_ffmpeg(source_path: str, output_path: str) -> None:
    """Ekstrahuje audio z pliku video do WAV używając ffmpeg."""
    subprocess.run(
        [
            "ffmpeg",
            "-i",
            source_path,
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            output_path,
        ],
        check=True,
        capture_output=True,
    )


def _read_text_file(path: Path, encoding: str) -> str:
    """Wczytuje plik tekstowy z podanym kodowaniem."""
    with open(path, "r", encoding=encoding) as f:
        return f.read()


class IngestionEngine:
    """
    Silnik przetwarzania wieloformatowych danych dla systemu pamięci Venom.
    Obsługuje: PDF, DOCX, obrazy, audio, video i tekst.
    """

    def __init__(self):
        """Inicjalizacja IngestionEngine."""
        self._vision_engine = None
        self._audio_engine = None
        logger.info("IngestionEngine zainicjalizowany")

    def _get_vision_engine(self):
        """Lazy loading dla vision engine (Florence-2)."""
        if self._vision_engine is None:
            try:
                from venom_core.perception.eyes import Eyes

                self._vision_engine = Eyes()
                logger.info("Vision Engine załadowany")
            except Exception as e:
                logger.warning(f"Nie udało się załadować Vision Engine: {e}")
                self._vision_engine = False
        return self._vision_engine if self._vision_engine is not False else None

    def _get_audio_engine(self):
        """Lazy loading dla audio engine (Whisper)."""
        if self._audio_engine is None:
            try:
                from venom_core.perception.audio_engine import WhisperSkill

                self._audio_engine = WhisperSkill(
                    model_size=SETTINGS.WHISPER_MODEL_SIZE,
                    device=SETTINGS.AUDIO_DEVICE,
                )
                logger.info("Audio Engine załadowany")
            except Exception as e:
                logger.warning(f"Nie udało się załadować Audio Engine: {e}")
                self._audio_engine = False
        return self._audio_engine if self._audio_engine is not False else None

    def detect_file_type(self, file_path: Path) -> str:
        """
        Wykrywa typ pliku na podstawie rozszerzenia i MIME type.

        Args:
            file_path: Ścieżka do pliku

        Returns:
            Typ pliku: 'pdf', 'docx', 'image', 'audio', 'video', 'text', 'unknown'
        """
        suffix = file_path.suffix.lower()
        mime_type, _ = mimetypes.guess_type(str(file_path))

        # PDF
        if suffix == ".pdf" or (mime_type and "pdf" in mime_type):
            return "pdf"

        # DOCX
        if suffix in [".docx", ".doc"] or (
            mime_type
            and (
                "word" in mime_type
                or mime_type
                == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        ):
            return "docx"

        # Obrazy
        if suffix in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"] or (
            mime_type and mime_type.startswith("image/")
        ):
            return "image"

        # Audio
        if suffix in [".mp3", ".wav", ".ogg", ".flac", ".m4a"] or (
            mime_type and mime_type.startswith("audio/")
        ):
            return "audio"

        # Video
        if suffix in [".mp4", ".avi", ".mkv", ".mov", ".webm"] or (
            mime_type and mime_type.startswith("video/")
        ):
            return "video"

        # Text
        if suffix in [".txt", ".md", ".rst", ".log"] or (
            mime_type and mime_type.startswith("text/")
        ):
            return "text"

        # Python, JavaScript, etc.
        if suffix in [".py", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".go", ".rs"]:
            return "text"

        return "unknown"

    async def ingest_file(
        self, file_path: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Przetwarza plik i zwraca ekstrahowane dane.

        Args:
            file_path: Ścieżka do pliku
            metadata: Opcjonalne metadane do dołączenia

        Returns:
            Dict z kluczami:
                - text: Ekstrahowany tekst
                - chunks: Lista fragmentów tekstowych
                - metadata: Wzbogacone metadane
                - file_type: Typ pliku
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Plik nie istnieje: {file_path}")

        file_type = self.detect_file_type(path)
        logger.info(f"Przetwarzanie pliku: {path.name} (typ: {file_type})")

        metadata = metadata or {}
        metadata["file_name"] = path.name
        metadata["file_path"] = str(path)
        metadata["file_type"] = file_type

        # Wybierz odpowiednią metodę przetwarzania
        if file_type == "pdf":
            text = await asyncio.to_thread(self._process_pdf, path)
        elif file_type == "docx":
            text = await asyncio.to_thread(self._process_docx, path)
        elif file_type == "image":
            text = await self._process_image(path)
        elif file_type == "audio":
            text = await self._process_audio(path)
        elif file_type == "video":
            text = await self._process_video(path)
        elif file_type == "text":
            text = await self._process_text(path)
        else:
            raise ValueError(f"Nieobsługiwany typ pliku: {file_type}")

        # Semantic chunking
        chunks = self._semantic_chunk(text)

        return {
            "text": text,
            "chunks": chunks,
            "metadata": metadata,
            "file_type": file_type,
        }

    def _process_pdf(self, path: Path) -> str:
        """
        Ekstrahuje tekst z pliku PDF.

        Args:
            path: Ścieżka do pliku PDF

        Returns:
            Ekstrahowany tekst
        """
        try:
            # Spróbuj użyć markitdown (Microsoft)
            try:
                from markitdown import MarkItDown

                md = MarkItDown()
                result = md.convert(str(path))
                if result and result.text_content:
                    logger.info(
                        f"PDF przetworzony (markitdown): {len(result.text_content)} znaków"
                    )
                    return result.text_content
            except ImportError:
                logger.debug("markitdown nie jest dostępny, próbuję pypdf")

            # Fallback do pypdf
            try:
                import pypdf

                reader = pypdf.PdfReader(str(path))
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n\n"

                logger.info(f"PDF przetworzony (pypdf): {len(text)} znaków")
                return text.strip()
            except ImportError:
                logger.error("Ani markitdown ani pypdf nie są dostępne")
                raise ImportError(
                    "Zainstaluj markitdown lub pypdf: pip install markitdown pypdf"
                )

        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania PDF: {e}")
            raise

    def _process_docx(self, path: Path) -> str:
        """
        Ekstrahuje tekst z pliku DOCX.

        Args:
            path: Ścieżka do pliku DOCX

        Returns:
            Ekstrahowany tekst
        """
        try:
            # Spróbuj użyć markitdown
            try:
                from markitdown import MarkItDown

                md = MarkItDown()
                result = md.convert(str(path))
                if result and result.text_content:
                    logger.info(
                        f"DOCX przetworzony (markitdown): {len(result.text_content)} znaków"
                    )
                    return result.text_content
            except ImportError:
                logger.debug("markitdown nie jest dostępny, próbuję python-docx")

            # Fallback do python-docx
            try:
                import docx

                doc = docx.Document(str(path))
                text = "\n\n".join([paragraph.text for paragraph in doc.paragraphs])

                logger.info(f"DOCX przetworzony (python-docx): {len(text)} znaków")
                return text.strip()
            except ImportError:
                logger.error("Ani markitdown ani python-docx nie są dostępne")
                raise ImportError(
                    "Zainstaluj markitdown lub python-docx: pip install markitdown python-docx"
                )

        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania DOCX: {e}")
            raise

    async def _process_image(self, path: Path) -> str:
        """
        Opisuje obraz używając Vision Engine (Florence-2).

        Args:
            path: Ścieżka do obrazu

        Returns:
            Opis obrazu
        """
        vision = self._get_vision_engine()
        if not vision:
            logger.warning("Vision Engine niedostępny, zwracam placeholder")
            return f"[Obraz: {path.name}]"

        try:
            # Użyj vision engine do opisu obrazu
            description = await asyncio.to_thread(
                vision.analyze_image,
                str(path),
                "Opisz szczegółowo co widzisz na tym obrazie.",
            )
            logger.info(f"Obraz przeanalizowany: {len(description)} znaków")
            return f"[Obraz: {path.name}]\n\n{description}"
        except Exception as e:
            logger.error(f"Błąd podczas analizy obrazu: {e}")
            return f"[Obraz: {path.name}] (błąd analizy: {str(e)})"

    async def _process_audio(self, path: Path) -> str:
        """
        Transkrybuje plik audio używając Whisper.

        Args:
            path: Ścieżka do pliku audio

        Returns:
            Transkrypcja
        """
        audio = self._get_audio_engine()
        if not audio:
            logger.warning("Audio Engine niedostępny, zwracam placeholder")
            return f"[Audio: {path.name}]"

        try:
            # Użyj Whisper do transkrypcji
            transcription = await asyncio.to_thread(audio.transcribe_file, str(path))
            logger.info(f"Audio transkrybowane: {len(transcription)} znaków")
            return f"[Audio: {path.name}]\n\nTranskrypcja:\n{transcription}"
        except Exception as e:
            logger.error(f"Błąd podczas transkrypcji audio: {e}")
            return f"[Audio: {path.name}] (błąd transkrypcji: {str(e)})"

    async def _process_video(self, path: Path) -> str:
        """
        Ekstrahuje audio z video i transkrybuje.

        Args:
            path: Ścieżka do pliku video

        Returns:
            Transkrypcja audio
        """
        # W przyszłości można dodać ekstrakcję klatek kluczowych
        logger.info(f"Przetwarzanie video: {path.name} (ekstrakcja audio)")

        try:
            # Sprawdź czy plik istnieje i jest plikiem
            if not path.is_file():
                raise ValueError(f"Invalid video file: {path}")

            # Użyj Path.resolve() dla bezpiecznej ścieżki
            safe_path = path.resolve()

            # Użyj ffmpeg do ekstrakcji audio (jeśli dostępne)
            tmp_path = await asyncio.to_thread(_create_temp_wav_file)

            # Ekstrahuj audio do WAV
            await asyncio.to_thread(
                _extract_audio_with_ffmpeg, str(safe_path), tmp_path
            )

            # Transkrybuj audio
            result = await self._process_audio(Path(tmp_path))

            # Usuń plik tymczasowy
            Path(tmp_path).unlink(missing_ok=True)

            return f"[Video: {path.name}]\n\n{result}"

        except FileNotFoundError:
            logger.warning("ffmpeg nie jest dostępny, zwracam placeholder")
            return f"[Video: {path.name}] (wymagany ffmpeg do ekstrakcji audio)"
        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania video: {e}")
            return f"[Video: {path.name}] (błąd: {str(e)})"

    async def _process_text(self, path: Path) -> str:
        """
        Wczytuje plik tekstowy.

        Args:
            path: Ścieżka do pliku tekstowego

        Returns:
            Zawartość pliku
        """
        try:
            text = await asyncio.to_thread(_read_text_file, path, "utf-8")
            logger.info(f"Plik tekstowy wczytany: {len(text)} znaków")
            return text
        except UnicodeDecodeError:
            # Spróbuj innych kodowań
            for encoding in ["latin-1", "cp1252", "iso-8859-1"]:
                try:
                    text = await asyncio.to_thread(_read_text_file, path, encoding)
                    logger.info(
                        f"Plik tekstowy wczytany ({encoding}): {len(text)} znaków"
                    )
                    return text
                except UnicodeDecodeError:
                    continue
            raise ValueError(f"Nie udało się zdekodować pliku: {path}")

    def _semantic_chunk(
        self, text: str, separators: Optional[List[str]] = None
    ) -> List[str]:
        """
        Dzieli tekst na fragmenty semantyczne (rekurencyjnie według hierarchii separatorów).

        Args:
            text: Tekst do podziału
            separators: Lista separatorów do użycia (domyślnie SEMANTIC_SEPARATORS)

        Returns:
            Lista fragmentów tekstowych
        """
        if separators is None:
            separators = SEMANTIC_SEPARATORS

        if len(text) <= SEMANTIC_CHUNK_SIZE:
            return [text]

        if not separators:
            # Brak separatorów, dziel po znakach
            parts = [
                text[i : i + SEMANTIC_CHUNK_SIZE]
                for i in range(0, len(text), SEMANTIC_CHUNK_SIZE)
            ]
            return [p.strip() for p in parts if p.strip()]

        separator = separators[0]
        if separator in text:
            parts = text.split(separator)
        else:
            # Próbuj z kolejnym separatorem
            return self._semantic_chunk(text, separators[1:])

        chunks = []
        current_chunk = ""

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Jeśli dodanie części nie przekroczy limitu, dodaj ją
            if len(current_chunk) + len(part) + len(separator) <= SEMANTIC_CHUNK_SIZE:
                current_chunk += part + separator
            else:
                # Zapisz obecny chunk jeśli nie jest pusty
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())

                # Rozpocznij nowy chunk
                if len(part) > SEMANTIC_CHUNK_SIZE:
                    # Jeśli część jest za duża, rekurencyjnie ją podziel z kolejnymi separatorami
                    sub_chunks = self._semantic_chunk(part, separators[1:])
                    chunks.extend(sub_chunks)
                    current_chunk = ""
                else:
                    current_chunk = part + separator

        # Dodaj ostatni chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        logger.info(f"Tekst podzielony na {len(chunks)} fragmentów semantycznych")
        return chunks

    async def ingest_url(
        self, url: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Pobiera i przetwarza zawartość strony WWW.

        Args:
            url: URL do pobrania
            metadata: Opcjonalne metadane

        Returns:
            Dict z ekstrahowanymi danymi
        """
        logger.info(f"Pobieranie URL: {url}")

        # Walidacja URL
        from urllib.parse import urlparse

        parsed = urlparse(url)
        # Blokuj localhost, private IP ranges, file:// etc.
        if parsed.scheme not in ["http", "https"]:
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
        if parsed.hostname in ["localhost", "127.0.0.1", "0.0.0.0"]:
            raise ValueError("Access to localhost is not allowed")

        try:
            import trafilatura

            # Pobierz i wyekstrahuj tekst
            downloaded = await asyncio.to_thread(trafilatura.fetch_url, url)
            if not downloaded:
                raise ValueError(f"Nie udało się pobrać URL: {url}")

            text = await asyncio.to_thread(
                trafilatura.extract,
                downloaded,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )

            if not text:
                raise ValueError(f"Nie udało się wyekstrahować tekstu z URL: {url}")

            metadata = metadata or {}
            metadata["source_url"] = url
            metadata["file_type"] = "web"

            chunks = self._semantic_chunk(text)

            logger.info(
                f"URL przetworzony: {len(text)} znaków, {len(chunks)} fragmentów"
            )

            return {
                "text": text,
                "chunks": chunks,
                "metadata": metadata,
                "file_type": "web",
            }

        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania URL: {e}")
            raise
