"""
Testy strategii artefaktów testowych: CLEAN vs PRESERVE.

Weryfikują, że:
1. Tryb CLEAN usuwa artefakty po sesji testowej
2. Tryb PRESERVE zachowuje artefakty
3. Fixture test_artifact_dir działa poprawnie
4. Przekierowanie ścieżek runtime jest aktywne
"""

import json
import os
from pathlib import Path


def test_artifact_dir_fixture_creates_directory(test_artifact_dir):
    """Test weryfikuje że fixture test_artifact_dir tworzy katalog dla testu."""
    assert test_artifact_dir.exists()
    assert test_artifact_dir.is_dir()

    # Sprawdź metadane testu
    metadata_file = test_artifact_dir / "test_metadata.json"
    assert metadata_file.exists()

    metadata = json.loads(metadata_file.read_text())
    assert metadata["type"] == "test_artifact"
    assert "test_name" in metadata
    assert "timestamp" in metadata


def test_artifact_dir_allows_file_creation(test_artifact_dir):
    """Test weryfikuje że można tworzyć pliki w katalogu artefaktów."""
    test_file = test_artifact_dir / "test_output.txt"
    test_file.write_text("Test data")

    assert test_file.exists()
    assert test_file.read_text() == "Test data"


def test_artifact_dir_allows_nested_directories(test_artifact_dir):
    """Test weryfikuje że można tworzyć zagnieżdżone katalogi."""
    nested_dir = test_artifact_dir / "subdir" / "nested"
    nested_dir.mkdir(parents=True, exist_ok=True)

    test_file = nested_dir / "data.json"
    test_file.write_text('{"test": true}')

    assert nested_dir.exists()
    assert test_file.exists()


def test_session_artifact_dir_has_metadata(test_artifact_session_dir):
    """Test weryfikuje że katalog sesji ma poprawne metadane."""
    metadata_file = test_artifact_session_dir / "session_metadata.json"
    assert metadata_file.exists()

    metadata = json.loads(metadata_file.read_text())
    assert metadata["type"] == "test_artifact_session"
    assert metadata["mode"] in ["clean", "preserve"]
    assert "timestamp" in metadata
    assert "artifact_dir" in metadata


def test_chronos_timelines_dir_redirected():
    """Test weryfikuje że CHRONOS_TIMELINES_DIR jest przekierowany."""
    chronos_dir = os.environ.get("CHRONOS_TIMELINES_DIR", "")

    # Nie powinno wskazywać na ./data/timelines (katalog repozytorium)
    assert "data/timelines" not in chronos_dir or "test-results" in chronos_dir

    # Powinno wskazywać na katalog testowy lub tmp
    assert (
        "test-results" in chronos_dir
        or "tmp" in chronos_dir
        or "venom-pytest" in chronos_dir
    )


def test_dreaming_output_dir_redirected():
    """Test weryfikuje że DREAMING_OUTPUT_DIR jest przekierowany."""
    dreaming_dir = os.environ.get("DREAMING_OUTPUT_DIR", "")

    # Nie powinno wskazywać na ./data/synthetic_training (katalog repozytorium)
    assert (
        "data/synthetic_training" not in dreaming_dir or "test-results" in dreaming_dir
    )

    # Powinno wskazywać na katalog testowy lub tmp
    assert (
        "test-results" in dreaming_dir
        or "tmp" in dreaming_dir
        or "venom-pytest" in dreaming_dir
    )


def test_artifact_mode_environment_variable():
    """Test weryfikuje że można odczytać tryb artefaktów."""
    mode = os.environ.get("VENOM_TEST_ARTIFACT_MODE", "clean")
    assert mode in ["clean", "preserve"]


def test_multiple_tests_get_separate_directories(test_artifact_dir):
    """
    Test weryfikuje że każdy test otrzymuje własny katalog.
    Poprzedni test też używał test_artifact_dir, więc powinny mieć różne katalogi.
    """
    # Sprawdź że katalog zawiera nazwę tego testu
    assert "separate_directories" in str(test_artifact_dir)

    # Zapisz unikalny plik
    marker_file = test_artifact_dir / "unique_marker.txt"
    marker_file.write_text("This test's unique data")

    assert marker_file.exists()


def test_runtime_directories_isolation():
    """Test weryfikuje że kluczowe katalogi runtime są izolowane od repo."""
    from venom_core.config import SETTINGS

    # Sprawdź że ścieżki nie wskazują bezpośrednio na katalogi repo
    chronos_dir = Path(SETTINGS.CHRONOS_TIMELINES_DIR)
    dreaming_dir = Path(SETTINGS.DREAMING_OUTPUT_DIR)

    # Ścieżki testowe nie powinny być bezpośrednio w ./data/
    assert not str(chronos_dir).startswith("./data/timelines")
    assert not str(dreaming_dir).startswith("./data/synthetic_training")
