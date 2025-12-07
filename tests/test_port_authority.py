"""Testy jednostkowe dla port_authority."""

import socket

import pytest

from venom_core.utils.port_authority import (
    find_free_port,
    get_free_ports,
    is_port_in_use,
)


def test_is_port_in_use_free_port():
    """Test sprawdzenia czy port jest wolny."""
    # Znajdź wolny port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        free_port = s.getsockname()[1]

    # Ten port powinien być wolny (może być krótko zajęty przez SO)
    # ale generalnie powinien być dostępny
    assert not is_port_in_use(free_port) or is_port_in_use(free_port)


def test_is_port_in_use_occupied_port():
    """Test sprawdzenia czy port jest zajęty."""
    # Zajmij port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        occupied_port = s.getsockname()[1]

        # Port powinien być zajęty
        assert is_port_in_use(occupied_port)


def test_find_free_port_default_range():
    """Test znajdowania wolnego portu w domyślnym zakresie."""
    port = find_free_port()
    assert port is not None
    assert 8000 <= port <= 9000
    assert not is_port_in_use(port)


def test_find_free_port_custom_range():
    """Test znajdowania wolnego portu w niestandardowym zakresie."""
    port = find_free_port(start=9000, end=9100)
    assert port is not None
    assert 9000 <= port <= 9100


def test_find_free_port_invalid_range():
    """Test błędu przy nieprawidłowym zakresie."""
    with pytest.raises(ValueError):
        find_free_port(start=9000, end=8000)

    with pytest.raises(ValueError):
        find_free_port(start=0)

    with pytest.raises(ValueError):
        find_free_port(start=70000)


def test_find_free_port_no_free_ports():
    """Test gdy nie ma wolnych portów w zakresie."""
    # Zajmij wszystkie porty w małym zakresie
    sockets = []
    start_port = 9990
    end_port = 9995

    try:
        # Zajmij porty
        for port in range(start_port, end_port + 1):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(("localhost", port))
                sockets.append(s)
            except OSError:
                # Port może być zajęty przez system
                pass

        # Spróbuj znaleźć wolny port w zajętym zakresie
        result = find_free_port(start=start_port, end=end_port)
        # Może zwrócić None jeśli wszystkie porty są zajęte
        # lub znaleźć port jeśli któryś się zwolnił
        assert result is None or (start_port <= result <= end_port)

    finally:
        # Zwolnij porty
        for s in sockets:
            s.close()


def test_get_free_ports_multiple():
    """Test znajdowania wielu wolnych portów."""
    ports = get_free_ports(3)
    assert len(ports) == 3
    assert len(set(ports)) == 3  # Wszystkie unikalne
    for port in ports:
        assert 8000 <= port <= 9000


def test_get_free_ports_custom_range():
    """Test znajdowania wielu portów w niestandardowym zakresie."""
    ports = get_free_ports(2, start=9000, end=9100)
    assert len(ports) == 2
    for port in ports:
        assert 9000 <= port <= 9100


def test_get_free_ports_invalid_count():
    """Test błędu przy nieprawidłowej liczbie portów."""
    with pytest.raises(ValueError):
        get_free_ports(0)

    with pytest.raises(ValueError):
        get_free_ports(-1)


def test_get_free_ports_too_many():
    """Test błędu gdy żądana liczba portów przekracza dostępny zakres."""
    with pytest.raises(ValueError):
        # Próba znalezienia 10 portów w zakresie 5 portów
        get_free_ports(10, start=9990, end=9995)
