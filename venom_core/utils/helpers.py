"""Moduł: helpers - Venom Standard Library dla operacji niskopoziomowych.

Ten moduł stanowi centralny punkt dostępu do bezpiecznych operacji I/O w całym projekcie.
Wszystkie funkcje posiadają:
- Pełne adnotacje typów (type hints)
- Szczegółowe docstringi
- Obsługę błędów (try-except z logowaniem)
- Walidację wejścia
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Optional, Union

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def read_file(
    file_path: Union[str, Path],
    encoding: str = "utf-8",
    raise_on_error: bool = False,
) -> Optional[str]:
    """
    Odczytuje zawartość pliku tekstowego w bezpieczny sposób.

    Args:
        file_path: Ścieżka do pliku (str lub Path)
        encoding: Kodowanie pliku (domyślnie 'utf-8')
        raise_on_error: Czy rzucić wyjątek przy błędzie (domyślnie False)

    Returns:
        Zawartość pliku jako string, lub None jeśli wystąpił błąd

    Raises:
        FileNotFoundError: Jeśli plik nie istnieje (tylko gdy raise_on_error=True)
        IOError: Jeśli wystąpił błąd odczytu (tylko gdy raise_on_error=True)

    Example:
        >>> content = read_file("config.txt")
        >>> if content:
        ...     print(f"Odczytano {len(content)} znaków")
    """
    try:
        path = Path(file_path)

        if not path.exists():
            logger.error(f"Plik nie istnieje: {file_path}")
            if raise_on_error:
                raise FileNotFoundError(f"Plik nie istnieje: {file_path}")
            return None

        if not path.is_file():
            logger.error(f"Ścieżka nie wskazuje na plik: {file_path}")
            if raise_on_error:
                raise IOError(f"Ścieżka nie wskazuje na plik: {file_path}")
            return None

        with open(path, "r", encoding=encoding) as f:
            content = f.read()

        logger.debug(f"Odczytano plik: {file_path} ({len(content)} znaków)")
        return content

    except FileNotFoundError:
        if raise_on_error:
            raise
        logger.error(f"Nie znaleziono pliku: {file_path}")
        return None
    except UnicodeDecodeError as e:
        logger.error(f"Błąd dekodowania pliku {file_path} z encoding={encoding}: {e}")
        if raise_on_error:
            raise IOError(f"Błąd dekodowania: {e}") from e
        return None
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd podczas odczytu pliku {file_path}: {e}")
        if raise_on_error:
            raise IOError(f"Błąd odczytu: {e}") from e
        return None


def write_file(
    file_path: Union[str, Path],
    content: str,
    encoding: str = "utf-8",
    create_dirs: bool = True,
    raise_on_error: bool = False,
) -> bool:
    """
    Zapisuje zawartość do pliku w bezpieczny sposób.

    Args:
        file_path: Ścieżka do pliku (str lub Path)
        content: Treść do zapisania
        encoding: Kodowanie pliku (domyślnie 'utf-8')
        create_dirs: Czy tworzyć katalogi nadrzędne jeśli nie istnieją
        raise_on_error: Czy rzucić wyjątek przy błędzie (domyślnie False)

    Returns:
        True jeśli zapis się powiódł, False w przeciwnym razie

    Raises:
        IOError: Jeśli wystąpił błąd zapisu (tylko gdy raise_on_error=True)

    Example:
        >>> success = write_file("output.txt", "Hello World")
        >>> if success:
        ...     print("Plik zapisany pomyślnie")
    """
    try:
        path = Path(file_path)

        # Walidacja - upewnij się że content jest stringiem
        if not isinstance(content, str):
            logger.warning(
                f"Content nie jest stringiem (typ: {type(content)}), konwertuję..."
            )
            content = str(content)

        # Utwórz katalogi nadrzędne jeśli wymagane
        if create_dirs and not path.parent.exists():
            logger.debug(f"Tworzę katalogi nadrzędne: {path.parent}")
            path.parent.mkdir(parents=True, exist_ok=True)

        # Zapisz plik
        with open(path, "w", encoding=encoding) as f:
            f.write(content)

        logger.debug(f"Zapisano plik: {file_path} ({len(content)} znaków)")
        return True

    except Exception as e:
        logger.error(f"Błąd podczas zapisu pliku {file_path}: {e}")
        if raise_on_error:
            raise IOError(f"Błąd zapisu: {e}") from e
        return False


def read_json(
    file_path: Union[str, Path], raise_on_error: bool = False
) -> Optional[dict]:
    """
    Odczytuje plik JSON i zwraca jako słownik.

    Args:
        file_path: Ścieżka do pliku JSON
        raise_on_error: Czy rzucić wyjątek przy błędzie (domyślnie False)

    Returns:
        Słownik z danymi JSON, lub None jeśli wystąpił błąd

    Raises:
        FileNotFoundError: Jeśli plik nie istnieje (tylko gdy raise_on_error=True)
        json.JSONDecodeError: Jeśli plik nie jest poprawnym JSON (tylko gdy raise_on_error=True)

    Example:
        >>> config = read_json("config.json")
        >>> if config:
        ...     print(f"Wczytano {len(config)} kluczy")
    """
    try:
        content = read_file(file_path, raise_on_error=True)
        if content is None:
            return None

        data = json.loads(content)
        logger.debug(f"Odczytano JSON: {file_path}")
        return data

    except json.JSONDecodeError as e:
        logger.error(f"Błąd parsowania JSON w pliku {file_path}: {e}")
        if raise_on_error:
            raise
        return None
    except Exception as e:
        logger.error(f"Błąd podczas odczytu JSON {file_path}: {e}")
        if raise_on_error:
            raise IOError(f"Błąd odczytu JSON: {e}") from e
        return None


def write_json(
    file_path: Union[str, Path],
    data: Any,
    indent: int = 2,
    create_dirs: bool = True,
    raise_on_error: bool = False,
) -> bool:
    """
    Zapisuje dane do pliku JSON w czytelnym formacie.

    Args:
        file_path: Ścieżka do pliku JSON
        data: Dane do zapisania (muszą być serializowalne do JSON)
        indent: Liczba spacji wcięcia (domyślnie 2, None = brak formatowania)
        create_dirs: Czy tworzyć katalogi nadrzędne jeśli nie istnieją
        raise_on_error: Czy rzucić wyjątek przy błędzie (domyślnie False)

    Returns:
        True jeśli zapis się powiódł, False w przeciwnym razie

    Raises:
        TypeError: Jeśli dane nie są serializowalne do JSON (tylko gdy raise_on_error=True)
        IOError: Jeśli wystąpił błąd zapisu (tylko gdy raise_on_error=True)

    Example:
        >>> data = {"name": "Venom", "version": "2.0"}
        >>> success = write_json("metadata.json", data)
    """
    try:
        # Serializuj do JSON
        json_content = json.dumps(data, indent=indent, ensure_ascii=False)

        # Zapisz używając write_file
        success = write_file(
            file_path, json_content, create_dirs=create_dirs, raise_on_error=True
        )

        if success:
            logger.debug(f"Zapisano JSON: {file_path}")
        return success

    except TypeError as e:
        logger.error(f"Dane nie są serializowalne do JSON: {e}")
        if raise_on_error:
            raise
        return False
    except Exception as e:
        logger.error(f"Błąd podczas zapisu JSON {file_path}: {e}")
        if raise_on_error:
            raise IOError(f"Błąd zapisu JSON: {e}") from e
        return False


def generate_hash(
    content: Union[str, bytes], algorithm: str = "sha256", encoding: str = "utf-8"
) -> str:
    """
    Generuje hash z podanej zawartości.

    Args:
        content: Treść do zahashowania (str lub bytes)
        algorithm: Algorytm hashowania (domyślnie 'sha256')
                  Dostępne: 'md5', 'sha1', 'sha256', 'sha512'
        encoding: Kodowanie dla stringów (domyślnie 'utf-8')

    Returns:
        Hash jako string heksadecymalny

    Raises:
        ValueError: Jeśli algorytm nie jest obsługiwany

    Example:
        >>> file_hash = generate_hash("Hello World")
        >>> print(f"SHA256: {file_hash}")
    """
    try:
        # Dostępne algorytmy
        available_algorithms = {"md5", "sha1", "sha256", "sha512"}

        if algorithm not in available_algorithms:
            raise ValueError(
                f"Nieobsługiwany algorytm: {algorithm}. "
                f"Dostępne: {', '.join(available_algorithms)}"
            )

        # Konwertuj string na bytes jeśli trzeba
        if isinstance(content, str):
            content_bytes = content.encode(encoding)
        else:
            content_bytes = content

        # Wygeneruj hash
        hash_obj = hashlib.new(algorithm)
        hash_obj.update(content_bytes)
        hash_value = hash_obj.hexdigest()

        logger.debug(f"Wygenerowano hash {algorithm}: {hash_value[:16]}...")
        return hash_value

    except Exception as e:
        logger.error(f"Błąd podczas generowania hashu: {e}")
        raise


def file_exists(file_path: Union[str, Path]) -> bool:
    """
    Sprawdza czy plik istnieje.

    Args:
        file_path: Ścieżka do pliku

    Returns:
        True jeśli plik istnieje, False w przeciwnym razie

    Example:
        >>> if file_exists("config.json"):
        ...     print("Config exists")
    """
    try:
        return Path(file_path).exists()
    except Exception as e:
        logger.error(f"Błąd podczas sprawdzania istnienia pliku {file_path}: {e}")
        return False


def ensure_dir(dir_path: Union[str, Path]) -> bool:
    """
    Upewnia się, że katalog istnieje. Tworzy go jeśli nie istnieje.

    Args:
        dir_path: Ścieżka do katalogu

    Returns:
        True jeśli katalog istnieje lub został utworzony, False przy błędzie

    Example:
        >>> ensure_dir("./logs")
        >>> # Teraz można bezpiecznie zapisywać do ./logs/
    """
    try:
        path = Path(dir_path)
        path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Katalog zapewniony: {dir_path}")
        return True
    except Exception as e:
        logger.error(f"Błąd podczas tworzenia katalogu {dir_path}: {e}")
        return False


def get_file_size(file_path: Union[str, Path]) -> Optional[int]:
    """
    Zwraca rozmiar pliku w bajtach.

    Args:
        file_path: Ścieżka do pliku

    Returns:
        Rozmiar pliku w bajtach, lub None jeśli plik nie istnieje

    Example:
        >>> size = get_file_size("large_file.bin")
        >>> if size:
        ...     print(f"Rozmiar: {size / 1024:.2f} KB")
    """
    try:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"Plik nie istnieje: {file_path}")
            return None

        size = path.stat().st_size
        logger.debug(f"Rozmiar pliku {file_path}: {size} bajtów")
        return size

    except Exception as e:
        logger.error(f"Błąd podczas pobierania rozmiaru pliku {file_path}: {e}")
        return None
