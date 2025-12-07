"""Moduł: shell_skill - wykonywanie komend shell z obsługą Docker Sandbox."""

import subprocess
from typing import Annotated

from semantic_kernel.functions import kernel_function

from venom_core.config import SETTINGS
from venom_core.infrastructure.docker_habitat import DockerHabitat
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ShellSkill:
    """
    Skill do bezpiecznego wykonywania komend shell.

    Domyślnie wykonuje komendy w Docker Sandbox (DockerHabitat).
    Może być skonfigurowany do wykonywania komend lokalnie dla specyficznych przypadków.
    """

    def __init__(self, use_sandbox: bool = True):
        """
        Inicjalizacja ShellSkill.

        Args:
            use_sandbox: Czy używać Docker Sandbox (domyślnie True).
                        Jeśli False, komendy wykonywane są lokalnie.
        """
        self.use_sandbox = use_sandbox and SETTINGS.ENABLE_SANDBOX

        if self.use_sandbox:
            try:
                self.habitat = DockerHabitat()
                logger.info("ShellSkill zainicjalizowany z Docker Sandbox")
            except Exception as e:
                logger.warning(f"Nie można zainicjalizować Docker Sandbox: {e}")
                logger.warning("Przełączanie na tryb lokalny")
                self.use_sandbox = False
                self.habitat = None
        else:
            self.habitat = None
            logger.info("ShellSkill zainicjalizowany w trybie lokalnym")

    @kernel_function(
        name="run_shell",
        description="Wykonuje komendę shell w bezpiecznym środowisku (sandbox) lub lokalnie.",
    )
    def run_shell(
        self,
        command: Annotated[str, "Komenda shell do wykonania"],
        timeout: Annotated[
            int, "Maksymalny czas wykonania w sekundach (domyślnie 30)"
        ] = 30,
    ) -> str:
        """
        Wykonuje komendę shell.

        Args:
            command: Komenda do wykonania
            timeout: Maksymalny czas wykonania w sekundach

        Returns:
            Wynik wykonania komendy (stdout + stderr)

        Raises:
            RuntimeError: Jeśli wykonanie się nie powiodło
        """
        if self.use_sandbox:
            return self._run_in_sandbox(command, timeout)
        else:
            return self._run_locally(command, timeout)

    def _run_in_sandbox(self, command: str, timeout: int) -> str:
        """
        Wykonuje komendę w Docker Sandbox.

        Args:
            command: Komenda do wykonania
            timeout: Maksymalny czas wykonania

        Returns:
            Wynik wykonania (stdout + stderr) z informacją o exit_code
        """
        try:
            logger.info(f"Wykonywanie w sandbox: {command[:100]}")
            exit_code, output = self.habitat.execute(command, timeout)

            if exit_code == 0:
                result = f"Komenda wykonana pomyślnie.\n\nOutput:\n{output}"
            else:
                result = f"Komenda zakończona z błędem (exit_code={exit_code}).\n\nOutput:\n{output}"

            logger.info(
                f"Wynik wykonania: exit_code={exit_code}, output_length={len(output)}"
            )
            return result

        except Exception as e:
            error_msg = f"Błąd podczas wykonywania komendy w sandbox: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _run_locally(self, command: str, timeout: int) -> str:
        """
        Wykonuje komendę lokalnie.

        Args:
            command: Komenda do wykonania
            timeout: Maksymalny czas wykonania

        Returns:
            Wynik wykonania (stdout + stderr) z informacją o exit_code
        """
        try:
            logger.info(f"Wykonywanie lokalnie: {command[:100]}")

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=SETTINGS.WORKSPACE_ROOT,
            )

            output = result.stdout + result.stderr

            if result.returncode == 0:
                result_msg = f"Komenda wykonana pomyślnie.\n\nOutput:\n{output}"
            else:
                result_msg = f"Komenda zakończona z błędem (exit_code={result.returncode}).\n\nOutput:\n{output}"

            logger.info(
                f"Wynik wykonania: exit_code={result.returncode}, output_length={len(output)}"
            )
            return result_msg

        except subprocess.TimeoutExpired:
            error_msg = f"Komenda przekroczyła limit czasu ({timeout}s)"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Błąd podczas wykonywania komendy lokalnie: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def get_exit_code_from_output(self, output: str) -> int:
        """
        Ekstrahuje exit_code z outputu run_shell.

        Args:
            output: Output z run_shell

        Returns:
            Exit code (0 = sukces, >0 = błąd)
        """
        if "exit_code=" in output:
            try:
                # Parsuj exit_code z outputu
                start = output.find("exit_code=") + len("exit_code=")
                end = output.find(")", start)
                return int(output[start:end])
            except (ValueError, IndexError):
                pass

        # Jeśli nie można sparsować, sprawdź czy był sukces
        if "wykonana pomyślnie" in output.lower():
            return 0
        else:
            return 1
