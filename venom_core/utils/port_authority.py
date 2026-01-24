"""Moduł: port_authority - zarządzanie portami i unikanie konfliktów."""

import socket
from typing import Optional

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


def is_port_in_use(port: int, host: str = "localhost") -> bool:
    """
    Sprawdza czy port jest zajęty.

    Args:
        port: Numer portu do sprawdzenia
        host: Host do sprawdzenia (domyślnie localhost)

    Returns:
        True jeśli port jest zajęty, False w przeciwnym razie

    Note:
        UWAGA: Ta funkcja ma potencjalny race condition - po sprawdzeniu że port
        jest wolny, socket jest zamykany, co oznacza że inny proces może zająć
        ten port przed jego użyciem. Jest to ograniczenie inherentne dla podejścia
        check-then-use. W praktyce ryzyko jest minimalne przy krótkim czasie
        między sprawdzeniem a użyciem.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return False
        except OSError:
            return True


def find_free_port(
    start: int = 8000, end: int = 9000, host: str = "localhost"
) -> Optional[int]:
    """
    Znajduje wolny port w określonym zakresie.

    Args:
        start: Początkowy numer portu (domyślnie 8000)
        end: Końcowy numer portu (domyślnie 9000)
        host: Host do sprawdzenia (domyślnie localhost)

    Returns:
        Numer wolnego portu lub None jeśli nie znaleziono wolnego portu

    Raises:
        ValueError: Jeśli zakres portów jest nieprawidłowy
    """
    if start < 1 or start > 65535:
        raise ValueError(f"Nieprawidłowy port początkowy: {start}")
    if end < 1 or end > 65535:
        raise ValueError(f"Nieprawidłowy port końcowy: {end}")
    if start >= end:
        raise ValueError(
            f"Port początkowy ({start}) musi być mniejszy niż końcowy ({end})"
        )

    for port in range(start, end + 1):
        if not is_port_in_use(port, host):
            logger.info(f"Znaleziono wolny port: {port}")
            return port

    logger.warning(f"Nie znaleziono wolnego portu w zakresie {start}-{end}")
    return None


def get_free_ports(
    count: int, start: int = 8000, end: int = 9000, host: str = "localhost"
) -> list[int]:
    """
    Znajduje określoną liczbę wolnych portów.

    Args:
        count: Liczba portów do znalezienia
        start: Początkowy numer portu (domyślnie 8000)
        end: Końcowy numer portu (domyślnie 9000)
        host: Host do sprawdzenia (domyślnie localhost)

    Returns:
        Lista wolnych portów

    Raises:
        ValueError: Jeśli nie można znaleźć wystarczającej liczby wolnych portów

    Note:
        UWAGA: Ta funkcja alokuje porty sekwencyjnie i ma potencjalny TOCTOU
        (Time-Of-Check-Time-Of-Use) problem. Porty nie są rezerwowane, więc
        mogą zostać zajęte przez inny proces między sprawdzeniem a użyciem.
        Używaj tej funkcji tylko gdy porty będą użyte natychmiast po alokacji.
    """
    if count < 1:
        raise ValueError("Liczba portów musi być większa od 0")

    free_ports: list[int] = []
    current_port = start

    while len(free_ports) < count and current_port <= end:
        if not is_port_in_use(current_port, host):
            free_ports.append(current_port)
            logger.debug(f"Dodano wolny port: {current_port}")
        current_port += 1

    if len(free_ports) < count:
        raise ValueError(
            f"Nie można znaleźć {count} wolnych portów w zakresie {start}-{end}. "
            f"Znaleziono tylko {len(free_ports)} portów."
        )

    logger.info(f"Znaleziono {count} wolnych portów: {free_ports}")
    return free_ports
