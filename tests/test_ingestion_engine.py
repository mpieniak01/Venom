"""Testy dla IngestionEngine."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from venom_core.memory.ingestion_engine import IngestionEngine


@pytest.fixture
def ingestion_engine():
    """Fixture dla IngestionEngine."""
    return IngestionEngine()


def test_ingestion_engine_init():
    """Test inicjalizacji IngestionEngine."""
    engine = IngestionEngine()
    assert engine is not None
    assert engine._vision_engine is None
    assert engine._audio_engine is None


def test_detect_file_type_pdf(ingestion_engine):
    """Test wykrywania typu pliku PDF."""
    path = Path("test.pdf")
    assert ingestion_engine.detect_file_type(path) == "pdf"


def test_detect_file_type_docx(ingestion_engine):
    """Test wykrywania typu pliku DOCX."""
    path = Path("test.docx")
    assert ingestion_engine.detect_file_type(path) == "docx"


def test_detect_file_type_image(ingestion_engine):
    """Test wykrywania typu pliku obrazu."""
    for ext in [".png", ".jpg", ".jpeg", ".gif"]:
        path = Path(f"test{ext}")
        assert ingestion_engine.detect_file_type(path) == "image"


def test_detect_file_type_audio(ingestion_engine):
    """Test wykrywania typu pliku audio."""
    for ext in [".mp3", ".wav", ".ogg"]:
        path = Path(f"test{ext}")
        assert ingestion_engine.detect_file_type(path) == "audio"


def test_detect_file_type_video(ingestion_engine):
    """Test wykrywania typu pliku video."""
    for ext in [".mp4", ".avi", ".mkv"]:
        path = Path(f"test{ext}")
        assert ingestion_engine.detect_file_type(path) == "video"


def test_detect_file_type_text(ingestion_engine):
    """Test wykrywania typu pliku tekstowego."""
    for ext in [".txt", ".md", ".py", ".js"]:
        path = Path(f"test{ext}")
        assert ingestion_engine.detect_file_type(path) == "text"


def test_semantic_chunk_short_text(ingestion_engine):
    """Test semantic chunking dla krótkiego tekstu."""
    text = "To jest krótki tekst."
    chunks = ingestion_engine._semantic_chunk(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_semantic_chunk_long_text(ingestion_engine):
    """Test semantic chunking dla długiego tekstu."""
    # Stwórz długi tekst (powyżej SEMANTIC_CHUNK_SIZE)
    text = "To jest akapit. " * 100  # ~1600 znaków
    chunks = ingestion_engine._semantic_chunk(text)
    assert len(chunks) > 1
    # Sprawdź czy chunki nie są puste
    for chunk in chunks:
        assert len(chunk) > 0


@pytest.mark.asyncio
async def test_process_text_file(tmp_path, ingestion_engine):
    """Test przetwarzania pliku tekstowego."""
    # Utwórz tymczasowy plik
    test_file = tmp_path / "test.txt"
    test_content = "To jest testowa treść pliku."
    test_file.write_text(test_content, encoding="utf-8")

    # Przetwórz plik
    result = await ingestion_engine._process_text(test_file)
    assert result == test_content


@pytest.mark.asyncio
async def test_ingest_file_not_found(ingestion_engine):
    """Test ingestii nieistniejącego pliku."""
    with pytest.raises(FileNotFoundError):
        await ingestion_engine.ingest_file("/nonexistent/file.txt")


@pytest.mark.asyncio
async def test_ingest_file_text(tmp_path, ingestion_engine):
    """Test ingestii pliku tekstowego."""
    # Utwórz tymczasowy plik
    test_file = tmp_path / "test.txt"
    test_content = "To jest testowa treść.\n\nDrugi akapit."
    test_file.write_text(test_content, encoding="utf-8")

    # Ingestia
    result = await ingestion_engine.ingest_file(str(test_file))

    assert result["text"] == test_content
    assert result["file_type"] == "text"
    assert len(result["chunks"]) > 0
    assert result["metadata"]["file_name"] == "test.txt"


@pytest.mark.asyncio
async def test_ingest_url_success(ingestion_engine):
    """Test ingestii URL (mock)."""
    with (
        patch("trafilatura.fetch_url") as mock_fetch,
        patch("trafilatura.extract") as mock_extract,
    ):
        # Mock trafilatura
        mock_fetch.return_value = "<html>Test content</html>"
        mock_extract.return_value = "Ekstrahowana treść z URL"

        result = await ingestion_engine.ingest_url("https://example.com")

        assert result["text"] == "Ekstrahowana treść z URL"
        assert result["file_type"] == "web"
        assert result["metadata"]["source_url"] == "https://example.com"
        assert len(result["chunks"]) > 0


@pytest.mark.asyncio
async def test_ingest_url_failure(ingestion_engine):
    """Test ingestii URL z błędem."""
    with patch("trafilatura.fetch_url") as mock_fetch:
        # Mock błąd
        mock_fetch.return_value = None

        with pytest.raises(ValueError, match="Nie udało się pobrać URL"):
            await ingestion_engine.ingest_url("https://example.com")


def test_get_vision_engine_lazy_load(ingestion_engine):
    """Test lazy loading vision engine."""
    # Początkowy stan
    assert ingestion_engine._vision_engine is None

    # Mock Eyes
    with patch("venom_core.perception.eyes.Eyes") as MockEyes:
        mock_eyes = Mock()
        MockEyes.return_value = mock_eyes

        # Pierwsze wywołanie - lazy load
        result = ingestion_engine._get_vision_engine()
        assert result is mock_eyes
        assert ingestion_engine._vision_engine is mock_eyes

        # Drugie wywołanie - używa cache
        result2 = ingestion_engine._get_vision_engine()
        assert result2 is mock_eyes
        MockEyes.assert_called_once()  # Tylko raz


def test_get_audio_engine_lazy_load(ingestion_engine):
    """Test lazy loading audio engine."""
    # Początkowy stan
    assert ingestion_engine._audio_engine is None

    # Mock WhisperSkill
    with patch("venom_core.perception.audio_engine.WhisperSkill") as MockWhisper:
        mock_whisper = Mock()
        MockWhisper.return_value = mock_whisper

        # Pierwsze wywołanie - lazy load
        result = ingestion_engine._get_audio_engine()
        assert result is mock_whisper
        assert ingestion_engine._audio_engine is mock_whisper

        # Drugie wywołanie - używa cache
        result2 = ingestion_engine._get_audio_engine()
        assert result2 is mock_whisper
        MockWhisper.assert_called_once()  # Tylko raz
