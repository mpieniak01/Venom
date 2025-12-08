"""Moduł: stack_manager - zarządzanie środowiskami Docker Compose."""

import shutil
import subprocess
from pathlib import Path
from typing import Optional

import docker

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


# Domyślny stack z Redis dla architektury Hive
# UWAGA: Ta konfiguracja jest dla developmentu. W produkcji użyj zabezpieczonej wersji z dokumentacji.
DEFAULT_HIVE_STACK = """version: '3.8'

services:
  redis:
    image: redis:alpine
    container_name: venom-hive-redis
    # Port bind do localhost tylko (bezpieczniejsze dla developmentu)
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    restart: unless-stopped
    networks:
      - venom-hive

networks:
  venom-hive:
    driver: bridge

volumes:
  redis_data:
"""


class StackManager:
    """
    Zarządca stacków Docker Compose.

    Umożliwia tworzenie, uruchamianie i zarządzanie środowiskami wielokontenerowymi
    przy użyciu docker-compose. Każdy stack ma swój izolowany katalog w workspace.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        """
        Inicjalizacja StackManager.

        Args:
            workspace_root: Katalog główny workspace (domyślnie z SETTINGS)
        """
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        self.stacks_dir = self.workspace_root / "stacks"
        self.stacks_dir.mkdir(parents=True, exist_ok=True)

        # Sprawdź czy docker-compose jest dostępny
        self._check_docker_compose()

        # Inicjalizuj klienta Docker (do sprawdzania statusu)
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            logger.warning(f"Nie można połączyć się z Docker daemon: {e}")
            self.docker_client = None

        logger.info(f"StackManager zainicjalizowany z workspace: {self.workspace_root}")

    def _check_docker_compose(self):
        """
        Sprawdza czy docker-compose jest dostępny.

        Raises:
            RuntimeError: Jeśli docker-compose nie jest dostępny
        """
        try:
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(f"Docker Compose dostępny: {result.stdout.strip()}")
            else:
                raise RuntimeError("Docker Compose nie odpowiada poprawnie")
        except (
            subprocess.TimeoutExpired,
            FileNotFoundError,
            subprocess.SubprocessError,
        ) as e:
            error_msg = f"Docker Compose nie jest dostępny: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _get_stack_dir(self, stack_name: str) -> Path:
        """
        Zwraca katalog dla danego stacka.

        Args:
            stack_name: Nazwa stacka

        Returns:
            Ścieżka do katalogu stacka
        """
        stack_dir = self.stacks_dir / stack_name
        stack_dir.mkdir(parents=True, exist_ok=True)
        return stack_dir

    def deploy_stack(
        self,
        compose_content: str,
        stack_name: str,
        project_name: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Wdraża stack Docker Compose.

        Args:
            compose_content: Zawartość pliku docker-compose.yml
            stack_name: Nazwa stacka (katalog w workspace/stacks/)
            project_name: Opcjonalna nazwa projektu Docker Compose
                         (domyślnie stack_name)

        Returns:
            Krotka (sukces, komunikat)
        """
        try:
            # Przygotuj katalog stacka
            stack_dir = self._get_stack_dir(stack_name)
            compose_file = stack_dir / "docker-compose.yml"

            # Zapisz plik docker-compose.yml
            compose_file.write_text(compose_content, encoding="utf-8")
            logger.info(f"Zapisano docker-compose.yml dla stacka: {stack_name}")

            # Ustal nazwę projektu
            proj_name = project_name or stack_name

            # Uruchom docker compose up
            cmd = [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-p",
                proj_name,
                "up",
                "-d",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(stack_dir),
                timeout=300,  # 5 minut timeout
            )

            if result.returncode == 0:
                msg = f"Stack '{stack_name}' wdrożony pomyślnie\n{result.stdout}"
                logger.info(msg)
                return True, msg
            else:
                msg = f"Błąd podczas wdrażania stacka '{stack_name}':\n{result.stderr}"
                logger.error(msg)
                return False, msg

        except subprocess.TimeoutExpired:
            msg = f"Timeout podczas wdrażania stacka '{stack_name}'"
            logger.error(msg)
            return False, msg
        except Exception as e:
            msg = f"Nieoczekiwany błąd podczas wdrażania stacka '{stack_name}': {e}"
            logger.error(msg)
            return False, msg

    def destroy_stack(
        self,
        stack_name: str,
        project_name: Optional[str] = None,
        remove_volumes: bool = True,
        cleanup_directory: bool = False,
    ) -> tuple[bool, str]:
        """
        Usuwa stack Docker Compose.

        Args:
            stack_name: Nazwa stacka
            project_name: Opcjonalna nazwa projektu (domyślnie stack_name)
            remove_volumes: Czy usunąć również wolumeny (domyślnie True)
            cleanup_directory: Czy usunąć katalog stacka po zniszczeniu (domyślnie False)

        Returns:
            Krotka (sukces, komunikat)
        """
        try:
            stack_dir = self._get_stack_dir(stack_name)
            compose_file = stack_dir / "docker-compose.yml"

            if not compose_file.exists():
                msg = f"Stack '{stack_name}' nie istnieje (brak docker-compose.yml)"
                logger.warning(msg)
                return False, msg

            # Ustal nazwę projektu
            proj_name = project_name or stack_name

            # Przygotuj komendę docker compose down
            cmd = [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-p",
                proj_name,
                "down",
            ]

            if remove_volumes:
                cmd.append("-v")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(stack_dir),
                timeout=120,  # 2 minuty timeout
            )

            if result.returncode == 0:
                msg = f"Stack '{stack_name}' usunięty pomyślnie\n{result.stdout}"
                logger.info(msg)

                # Opcjonalne czyszczenie katalogu
                if cleanup_directory:
                    try:
                        shutil.rmtree(stack_dir)
                        logger.info(f"Katalog stacka '{stack_name}' został usunięty")
                        msg += "\nKatalog stacka został usunięty z workspace"
                    except Exception as e:
                        logger.warning(f"Nie można usunąć katalogu stacka: {e}")
                        msg += f"\nUWAGA: Nie można usunąć katalogu: {e}"

                return True, msg
            else:
                msg = f"Błąd podczas usuwania stacka '{stack_name}':\n{result.stderr}"
                logger.error(msg)
                return False, msg

        except subprocess.TimeoutExpired:
            msg = f"Timeout podczas usuwania stacka '{stack_name}'"
            logger.error(msg)
            return False, msg
        except Exception as e:
            msg = f"Nieoczekiwany błąd podczas usuwania stacka '{stack_name}': {e}"
            logger.error(msg)
            return False, msg

    def get_service_logs(
        self,
        stack_name: str,
        service: str,
        project_name: Optional[str] = None,
        tail: int = 100,
    ) -> tuple[bool, str]:
        """
        Pobiera logi konkretnego serwisu w stacku.

        Args:
            stack_name: Nazwa stacka
            service: Nazwa serwisu w docker-compose.yml
            project_name: Opcjonalna nazwa projektu (domyślnie stack_name)
            tail: Liczba ostatnich linii do pobrania (domyślnie 100)

        Returns:
            Krotka (sukces, logi)
        """
        try:
            stack_dir = self._get_stack_dir(stack_name)
            compose_file = stack_dir / "docker-compose.yml"

            if not compose_file.exists():
                msg = f"Stack '{stack_name}' nie istnieje"
                logger.warning(msg)
                return False, msg

            # Ustal nazwę projektu
            proj_name = project_name or stack_name

            # Pobierz logi
            cmd = [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "-p",
                proj_name,
                "logs",
                "--tail",
                str(tail),
                service,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(stack_dir),
                timeout=30,
            )

            if result.returncode == 0:
                return True, result.stdout
            else:
                msg = f"Błąd podczas pobierania logów serwisu '{service}':\n{result.stderr}"
                logger.error(msg)
                return False, msg

        except subprocess.TimeoutExpired:
            msg = f"Timeout podczas pobierania logów serwisu '{service}'"
            logger.error(msg)
            return False, msg
        except Exception as e:
            msg = f"Nieoczekiwany błąd podczas pobierania logów: {e}"
            logger.error(msg)
            return False, msg

    def get_running_stacks(self) -> list[dict]:
        """
        Zwraca listę aktywnych stacków.

        Returns:
            Lista słowników z informacjami o stackach
        """
        running_stacks = []

        try:
            # Przejrzyj katalogi stacków
            for stack_dir in self.stacks_dir.iterdir():
                if not stack_dir.is_dir():
                    continue

                compose_file = stack_dir / "docker-compose.yml"
                if not compose_file.exists():
                    continue

                stack_name = stack_dir.name

                # Sprawdź status stacka
                try:
                    result = subprocess.run(
                        [
                            "docker",
                            "compose",
                            "-f",
                            str(compose_file),
                            "-p",
                            stack_name,
                            "ps",
                            "--format",
                            "json",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    if result.returncode == 0 and result.stdout.strip():
                        # Stack ma działające kontenery
                        running_stacks.append(
                            {
                                "name": stack_name,
                                "path": str(stack_dir),
                                "compose_file": str(compose_file),
                                "status": "running",
                            }
                        )
                except Exception as e:
                    logger.debug(
                        f"Nie można sprawdzić statusu stacka {stack_name}: {e}"
                    )

            logger.info(f"Znaleziono {len(running_stacks)} aktywnych stacków")
            return running_stacks

        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania aktywnych stacków: {e}")
            return []

    def get_stack_status(
        self, stack_name: str, project_name: Optional[str] = None
    ) -> tuple[bool, dict]:
        """
        Pobiera status stacka.

        Args:
            stack_name: Nazwa stacka
            project_name: Opcjonalna nazwa projektu (domyślnie stack_name)

        Returns:
            Krotka (sukces, słownik ze statusem)
        """
        try:
            stack_dir = self._get_stack_dir(stack_name)
            compose_file = stack_dir / "docker-compose.yml"

            if not compose_file.exists():
                return False, {"error": f"Stack '{stack_name}' nie istnieje"}

            proj_name = project_name or stack_name

            # Pobierz status kontenerów
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    proj_name,
                    "ps",
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return True, {
                    "stack_name": stack_name,
                    "status": "running" if result.stdout.strip() else "stopped",
                    "details": result.stdout,
                }
            else:
                return False, {"error": result.stderr}

        except Exception as e:
            return False, {"error": str(e)}

    def deploy_default_hive_stack(self) -> tuple[bool, str]:
        """
        Wdraża domyślny stack Hive z Redis.

        Returns:
            Krotka (sukces, komunikat)
        """
        logger.info("Wdrażanie domyślnego stacka Hive (Redis)...")
        return self.deploy_stack(
            compose_content=DEFAULT_HIVE_STACK,
            stack_name="venom-hive",
            project_name="venom-hive",
        )
