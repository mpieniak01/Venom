import pytest

from venom_core.memory.ingestion_engine import SEMANTIC_CHUNK_SIZE, IngestionEngine


def test_detect_file_type_variants(tmp_path):
    engine = IngestionEngine()
    assert engine.detect_file_type(tmp_path / "file.pdf") == "pdf"
    assert engine.detect_file_type(tmp_path / "file.docx") == "docx"
    assert engine.detect_file_type(tmp_path / "file.png") == "image"
    assert engine.detect_file_type(tmp_path / "file.mp3") == "audio"
    assert engine.detect_file_type(tmp_path / "file.mp4") == "video"
    assert engine.detect_file_type(tmp_path / "file.txt") == "text"
    assert engine.detect_file_type(tmp_path / "file.py") == "text"
    assert engine.detect_file_type(tmp_path / "file.unknown") == "unknown"


def test_semantic_chunk_splits_long_text():
    engine = IngestionEngine()
    text = ("A " * (SEMANTIC_CHUNK_SIZE + 50)).strip()
    chunks = engine._semantic_chunk(text)
    assert len(chunks) >= 2
    assert all(len(chunk) <= SEMANTIC_CHUNK_SIZE for chunk in chunks)


@pytest.mark.asyncio
async def test_ingest_url_rejects_invalid_scheme():
    engine = IngestionEngine()
    with pytest.raises(ValueError):
        await engine.ingest_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_ingest_url_rejects_localhost():
    engine = IngestionEngine()
    with pytest.raises(ValueError):
        await engine.ingest_url("http://localhost:8000/health")
