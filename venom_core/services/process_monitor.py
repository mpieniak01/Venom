"""
Moduł: process_monitor - Monitorowanie procesów i odczyt statusów.

Odpowiada za:
- Odczyt plików PID
- Pobieranie informacji o procesach (CPU, RAM, uptime)
- Odczyt logów
- Sprawdzanie portów
"""

import time
from pathlib import Path
from typing import Dict, Optional

import psutil

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ProcessMonitor:
    """Monitor do odczytu statusów procesów i logów."""

    def __init__(self, project_root: Path):
        """
        Inicjalizacja monitora.

        Args:
            project_root: Ścieżka do katalogu głównego projektu
        """
        self.project_root = project_root

    def get_process_info(self, pid: int) -> Optional[Dict]:
        """
        Pobiera informacje o procesie.

        Args:
            pid: PID procesu

        Returns:
            Słownik z informacjami o procesie lub None jeśli proces nie istnieje
        """
        try:
            process = psutil.Process(pid)
            if not process.is_running():
                return None

            # Pobierz informacje o procesie
            cpu_percent = process.cpu_percent(interval=0.1)
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)  # Bytes to MB

            # Czas działania
            create_time = process.create_time()
            uptime_seconds = int(time.time() - create_time)

            return {
                "pid": pid,
                "cpu_percent": cpu_percent,
                "memory_mb": memory_mb,
                "uptime_seconds": uptime_seconds,
                "is_running": True,
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
            return None
        except Exception as e:
            logger.warning(f"Błąd podczas pobierania informacji o procesie {pid}: {e}")
            return None

    def read_pid_from_file(self, pid_file: Path) -> Optional[int]:
        """
        Odczytuje PID z pliku.

        Args:
            pid_file: Ścieżka do pliku PID

        Returns:
            PID lub None jeśli plik nie istnieje lub jest nieprawidłowy
        """
        if not pid_file.exists():
            return None

        try:
            pid_str = pid_file.read_text().strip()
            if not pid_str:
                return None
            return int(pid_str)
        except (ValueError, OSError) as e:
            logger.warning(f"Błąd podczas odczytu PID z {pid_file}: {e}")
            return None

    def read_last_log_line(self, log_file: Path, max_lines: int = 5) -> Optional[str]:
        """
        Odczytuje ostatnią linię z pliku logu.

        Args:
            log_file: Ścieżka do pliku logu
            max_lines: Maksymalna liczba linii do odczytu

        Returns:
            Ostatnia linia logu lub None
        """
        if not log_file.exists():
            return None

        try:
            with log_file.open("r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                if not lines:
                    return None
                # Weź ostatnie N linii i połącz je
                relevant_lines = lines[-max_lines:]
                return " | ".join(line.strip() for line in relevant_lines if line.strip())
        except Exception as e:
            logger.warning(f"Błąd podczas odczytu logu z {log_file}: {e}")
            return None

    def check_port_listening(self, port: int) -> bool:
        """
        Sprawdza czy port jest nasłuchiwany.

        Args:
            port: Numer portu

        Returns:
            True jeśli port jest otwarty i nasłuchiwany
        """
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == "LISTEN" and conn.laddr.port == port:
                    return True
            return False
        except (PermissionError, psutil.AccessDenied):
            logger.warning(f"Brak uprawnień do sprawdzenia portu {port}")
            return False
        except Exception as e:
            logger.warning(f"Błąd podczas sprawdzania portu {port}: {e}")
            return False

    def is_process_running(self, pid: int) -> bool:
        """
        Sprawdza czy proces o danym PID działa.

        Args:
            pid: PID procesu

        Returns:
            True jeśli proces działa
        """
        try:
            process = psutil.Process(pid)
            return process.is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
            return False
