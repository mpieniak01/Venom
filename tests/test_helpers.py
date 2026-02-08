"""Testy jednostkowe dla modułu helpers (Venom Standard Library)."""

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from venom_core.utils.helpers import (
    ensure_dir,
    file_exists,
    generate_hash,
    get_file_size,
    read_file,
    read_json,
    write_file,
    write_json,
)


@pytest.fixture
def temp_dir():
    """Fixture dla tymczasowego katalogu."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_write_and_read_file(temp_dir):
    """Test zapisu i odczytu pliku tekstowego."""
    file_path = temp_dir / "test.txt"
    content = "Hello, Venom!"

    # Zapisz plik
    assert write_file(file_path, content) is True
    assert file_path.exists()

    # Odczytaj plik
    read_content = read_file(file_path)
    assert read_content == content


def test_read_file_not_found(temp_dir):
    """Test odczytu nieistniejącego pliku."""
    file_path = temp_dir / "nonexistent.txt"

    # Bez raise_on_error - powinno zwrócić None
    content = read_file(file_path, raise_on_error=False)
    assert content is None

    # Z raise_on_error - powinno rzucić wyjątek
    with pytest.raises(FileNotFoundError):
        read_file(file_path, raise_on_error=True)


def test_write_file_creates_directories(temp_dir):
    """Test tworzenia katalogów nadrzędnych."""
    file_path = temp_dir / "subdir" / "nested" / "file.txt"
    content = "Nested file"

    assert write_file(file_path, content, create_dirs=True) is True
    assert file_path.exists()
    assert read_file(file_path) == content


def test_write_file_non_string_content(temp_dir):
    """Test zapisu zawartości niebędącej stringiem."""
    file_path = temp_dir / "number.txt"

    # Powinno automatycznie skonwertować na string
    non_string_content: Any = 12345
    assert write_file(file_path, non_string_content) is True
    assert read_file(file_path) == "12345"


def test_read_write_json(temp_dir):
    """Test zapisu i odczytu JSON."""
    file_path = temp_dir / "data.json"
    data = {"name": "Venom", "version": 2.0, "features": ["AI", "Automation"]}

    # Zapisz JSON
    assert write_json(file_path, data) is True
    assert file_path.exists()

    # Odczytaj JSON
    read_data = read_json(file_path)
    assert read_data == data


def test_read_json_invalid_file(temp_dir):
    """Test odczytu niepoprawnego JSON."""
    file_path = temp_dir / "invalid.json"

    # Zapisz niepoprawny JSON
    write_file(file_path, "{invalid json content")

    # Bez raise_on_error - powinno zwrócić None
    data = read_json(file_path, raise_on_error=False)
    assert data is None

    # Z raise_on_error - powinno rzucić wyjątek
    with pytest.raises(json.JSONDecodeError):
        read_json(file_path, raise_on_error=True)


def test_generate_hash_string():
    """Test generowania hashu ze stringa."""
    content = "Hello World"

    # SHA256 (domyślny)
    hash_sha256 = generate_hash(content)
    assert len(hash_sha256) == 64  # SHA256 ma 64 znaki hex

    # MD5
    hash_md5 = generate_hash(content, algorithm="md5")
    assert len(hash_md5) == 32  # MD5 ma 32 znaki hex

    # SHA512
    hash_sha512 = generate_hash(content, algorithm="sha512")
    assert len(hash_sha512) == 128  # SHA512 ma 128 znaków hex


def test_generate_hash_bytes():
    """Test generowania hashu z bytes."""
    content_bytes = b"Hello World"
    hash_value = generate_hash(content_bytes)
    assert len(hash_value) == 64


def test_generate_hash_invalid_algorithm():
    """Test generowania hashu z nieprawidłowym algorytmem."""
    with pytest.raises(ValueError, match="Nieobsługiwany algorytm"):
        generate_hash("test", algorithm="invalid")


def test_file_exists_check(temp_dir):
    """Test sprawdzania istnienia pliku."""
    existing_file = temp_dir / "exists.txt"
    nonexistent_file = temp_dir / "does_not_exist.txt"

    # Utwórz plik
    write_file(existing_file, "content")

    assert file_exists(existing_file) is True
    assert file_exists(nonexistent_file) is False


def test_ensure_dir(temp_dir):
    """Test tworzenia katalogu."""
    new_dir = temp_dir / "new" / "nested" / "dir"

    assert not new_dir.exists()
    assert ensure_dir(new_dir) is True
    assert new_dir.exists()

    # Wywołanie ponowne nie powinno powodować błędu
    assert ensure_dir(new_dir) is True


def test_get_file_size(temp_dir):
    """Test pobierania rozmiaru pliku."""
    file_path = temp_dir / "sized.txt"
    content = "X" * 1000  # 1000 znaków

    write_file(file_path, content)

    size = get_file_size(file_path)
    assert size == 1000  # Każdy znak 'X' to 1 bajt w UTF-8


def test_get_file_size_nonexistent(temp_dir):
    """Test pobierania rozmiaru nieistniejącego pliku."""
    file_path = temp_dir / "nonexistent.txt"
    size = get_file_size(file_path)
    assert size is None


def test_read_file_with_encoding(temp_dir):
    """Test odczytu pliku z różnymi kodowaniami."""
    file_path = temp_dir / "encoded.txt"

    # Zapisz z encoding UTF-8
    content = "Zażółć gęślą jaźń"
    write_file(file_path, content, encoding="utf-8")

    # Odczytaj z encoding UTF-8
    read_content = read_file(file_path, encoding="utf-8")
    assert read_content == content


def test_write_json_with_nested_data(temp_dir):
    """Test zapisu JSON z zagnieżdżonymi strukturami."""
    file_path = temp_dir / "nested.json"
    data = {
        "level1": {
            "level2": {"level3": {"value": 42}},
            "array": [1, 2, 3, {"nested": True}],
        }
    }

    assert write_json(file_path, data) is True

    # Sprawdź że można odczytać
    read_data = read_json(file_path)
    assert read_data == data


def test_write_json_non_serializable(temp_dir):
    """Test zapisu nieserializowalnych danych do JSON."""
    file_path = temp_dir / "invalid.json"

    # Funkcja nie jest serializowalna do JSON
    data = {"function": lambda x: x + 1}

    # Bez raise_on_error - powinno zwrócić False
    assert write_json(file_path, data, raise_on_error=False) is False

    # Z raise_on_error - powinno rzucić wyjątek
    with pytest.raises(TypeError):
        write_json(file_path, data, raise_on_error=True)


def test_read_file_not_a_file(temp_dir):
    """Test próby odczytu katalogu jako pliku."""
    dir_path = temp_dir / "subdir"
    dir_path.mkdir()

    # Bez raise_on_error - powinno zwrócić None
    content = read_file(dir_path, raise_on_error=False)
    assert content is None

    # Z raise_on_error - powinno rzucić IOError
    with pytest.raises(IOError):
        read_file(dir_path, raise_on_error=True)


def test_hash_consistency():
    """Test spójności hashowania - ten sam content powinien dawać ten sam hash."""
    content = "Consistent content"

    hash1 = generate_hash(content)
    hash2 = generate_hash(content)

    assert hash1 == hash2


def test_helpers_with_path_objects(temp_dir):
    """Test używania obiektów Path zamiast stringów."""
    file_path = temp_dir / "pathobj.txt"
    content = "Path object test"

    # Wszystkie funkcje powinny akceptować Path
    assert write_file(file_path, content) is True
    assert file_exists(file_path) is True
    assert read_file(file_path) == content
    assert get_file_size(file_path) == len(content)
