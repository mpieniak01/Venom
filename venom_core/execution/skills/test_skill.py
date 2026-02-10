"""Moduł: test_skill - wrapper na narzędzia testowe w DockerHabitat."""

from dataclasses import dataclass
from typing import Annotated, List, Optional

from semantic_kernel.functions import kernel_function

from venom_core.infrastructure.docker_habitat import DockerHabitat
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TestReport:
    """Raport z wykonania testów pytest."""

    __test__ = False

    exit_code: int
    passed: int
    failed: int
    failures: List[str]  # Szczegóły błędów
    raw_output: str  # Surowy output dla dodatkowej analizy


@dataclass
class LintReport:
    """Raport z wykonania lintera."""

    __test__ = False

    exit_code: int
    issues: List[str]  # Lista problemów znalezionych przez linter
    raw_output: str


class TestSkill:
    """
    Skill do uruchamiania testów i lintera w izolowanym środowisku Docker.

    Używa DockerHabitat do bezpiecznego wykonywania komend testowych.
    NIE uruchamia testów lokalnie - wszystko w kontenerze.
    """

    __test__ = False

    def __init__(
        self,
        habitat: Optional[DockerHabitat] = None,
        allow_local_execution: bool = False,
    ):
        """
        Inicjalizacja TestSkill.

        Args:
            habitat: Instancja DockerHabitat (jeśli None, zostanie utworzona)
            allow_local_execution: Czy zezwolić na uruchamianie testów lokalnie (bez sandboxa)
        """
        self.allow_local_execution = allow_local_execution

        # Próbuj użyć habitat jeśli dostępny
        self.habitat: Optional[DockerHabitat] = None
        try:
            self.habitat = habitat or DockerHabitat()
            self.docker_available = True
            logger.info("TestSkill zainicjalizowany (Docker sandbox)")
        except RuntimeError as e:
            # Środowisko docelowe (np. CI) może nie mieć Dockera
            self.habitat = None
            self.docker_available = False
            mode_msg = (
                "w trybie LOKALNYM (niebezpiecznym)"
                if self.allow_local_execution
                else "w trybie tylko-raportującym"
            )
            logger.warning(
                "DockerHabitat niedostępny (%s). TestSkill działa %s.", e, mode_msg
            )

    @kernel_function(
        name="run_pytest",
        description="Uruchamia testy pytest w kontenerze Docker (lub lokalnie) i parsuje wyniki.",
    )
    async def run_pytest(
        self,
        test_path: Annotated[
            str, "Ścieżka do testów (domyślnie '.' dla wszystkich)"
        ] = ".",
        timeout: Annotated[int, "Timeout w sekundach"] = 60,
    ) -> str:
        """
        Uruchamia pytest w kontenerze i parsuje wyniki.

        Args:
            test_path: Ścieżka do testów
            timeout: Maksymalny czas wykonania

        Returns:
            Sformatowany raport z wyników testów
        """
        try:
            # Walidacja test_path - zapobieganie command injection (nawet lokalnie to dobra praktyka)
            import re

            if not re.match(r"^[a-zA-Z0-9_./\-]+$", test_path):
                return f"❌ Błąd: Nieprawidłowa ścieżka testów: {test_path}"

            import shlex

            safe_path = shlex.quote(test_path)

            # --- Tryb Docker Sandbox ---
            if self.docker_available and self.habitat:
                logger.info(f"Uruchamiam pytest w Dockerze dla: {test_path}")
                command = f"python -m pytest {safe_path} -v --tb=short --color=no"
                exit_code, output = self.habitat.execute(command, timeout=timeout)

            # --- Tryb Lokalny (Fallback) ---
            elif self.allow_local_execution:
                logger.warning(f"⚠️ Uruchamiam pytest LOKALNIE dla: {test_path}")
                import asyncio
                import subprocess
                import sys

                # Używamy sys.executable aby mieć pewność że to ten sam venv
                cmd = [
                    sys.executable,
                    "-m",
                    "pytest",
                    test_path,
                    "-v",
                    "--tb=short",
                    "--color=no",
                ]

                try:
                    # Uruchomienie lokalne
                    process = await asyncio.create_subprocess_exec(
                        *cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                    )

                    try:
                        stdout, _ = await asyncio.wait_for(
                            process.communicate(), timeout=timeout
                        )
                        output = stdout.decode("utf-8", errors="replace")
                        exit_code = (
                            process.returncode if process.returncode is not None else 1
                        )
                    except asyncio.TimeoutError:
                        process.kill()
                        return f"❌ Przekroczono limit czasu ({timeout}s) podczas uruchamiania testów lokalnie."

                except Exception as e:
                    return f"❌ Błąd uruchamiania lokalnego procesu: {str(e)}"

            # --- Tryb Niedostępny ---
            else:
                return "⚠️ Docker sandbox jest niedostępny, a uruchamianie lokalne jest wyłączone."

            # Sparsuj wyniki (wspólne dla obu trybów)
            report = self._parse_pytest_output(exit_code, output)

            # Sformatuj raport do zwrócenia
            result = self._format_test_report(report)

            logger.info(
                f"Pytest zakończony: exit_code={exit_code}, passed={report.passed}, failed={report.failed}"
            )

            return result

        except Exception as e:
            error_msg = f"❌ Błąd podczas uruchamiania pytest: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="run_linter",
        description="Uruchamia linter (ruff) w kontenerze Docker (lub lokalnie).",
    )
    async def run_linter(
        self,
        path: Annotated[str, "Ścieżka do sprawdzenia (domyślnie '.')"] = ".",
        timeout: Annotated[int, "Timeout w sekundach"] = 30,
    ) -> str:
        """
        Uruchamia ruff linter w kontenerze.

        Args:
            path: Ścieżka do plików do sprawdzenia
            timeout: Maksymalny czas wykonania

        Returns:
            Sformatowany raport z lintera
        """
        try:
            if not self._is_valid_lint_path(path):
                return f"❌ Błąd: Nieprawidłowa ścieżka: {path}"

            if self.docker_available and self.habitat:
                exit_code, output = self._run_linter_in_docker(path, timeout)
            elif self.allow_local_execution:
                local_result = await self._run_linter_locally(path, timeout)
                if isinstance(local_result, str):
                    return local_result
                exit_code, output = local_result
            else:
                return "⚠️ Docker sandbox jest niedostępny, a uruchamianie lokalne jest wyłączone."

            # Sparsuj wyniki
            report = self._parse_linter_output(exit_code, output)

            # Sformatuj raport
            result = self._format_lint_report(report)

            logger.info(
                f"Linter zakończony: exit_code={exit_code}, issues={len(report.issues)}"
            )

            return result

        except Exception as e:
            error_msg = f"❌ Błąd podczas uruchamiania lintera: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @staticmethod
    def _is_valid_lint_path(path: str) -> bool:
        import re

        return bool(re.match(r"^[a-zA-Z0-9_./\-]+$", path))

    def _run_linter_in_docker(self, path: str, timeout: int) -> tuple[int, str]:
        import shlex

        safe_path = shlex.quote(path)
        logger.info(f"Uruchamiam linter w Dockerze dla: {path}")
        command = f"python -m ruff check {safe_path} || python -m flake8 {safe_path}"
        assert self.habitat is not None
        return self.habitat.execute(command, timeout=timeout)

    async def _run_linter_locally(
        self, path: str, timeout: int
    ) -> tuple[int, str] | str:
        logger.warning(f"⚠️ Uruchamiam linter LOKALNIE dla: {path}")
        local_ruff = await self._run_local_linter_binary("ruff", path, timeout)
        if local_ruff is not None:
            return local_ruff

        local_flake8 = await self._run_local_linter_binary("flake8", path, timeout)
        if local_flake8 is not None:
            return local_flake8
        return (
            "❌ Błąd uruchamiania lintera lokalnie: brak ruff/flake8 lub błąd wykonania"
        )

    async def _run_local_linter_binary(
        self, binary: str, path: str, timeout: int
    ) -> tuple[int, str] | None:
        import asyncio
        import subprocess
        import sys

        cmd = [sys.executable, "-m", binary, "check", path]
        if binary == "flake8":
            cmd = [sys.executable, "-m", "flake8", path]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
            output = stdout.decode()
            exit_code = process.returncode if process.returncode is not None else 1
            return exit_code, output
        except Exception:
            return None

    def _parse_pytest_output(self, exit_code: int, output: str) -> TestReport:
        """
        Parsuje output pytest do struktury TestReport.

        Args:
            exit_code: Kod wyjścia pytest
            output: Surowy output

        Returns:
            Obiekt TestReport
        """
        lines = output.split("\n")
        passed, failed = self._extract_pytest_summary(lines)
        failures = self._extract_pytest_failures(lines)

        # Jeśli nie znaleziono podsumowania, spróbuj alternatywnej metody
        if passed == 0 and failed == 0 and exit_code != 0:
            passed, failed = self._fallback_count_tests(lines)

        return TestReport(
            exit_code=exit_code,
            passed=passed,
            failed=failed,
            failures=failures,
            raw_output=output,
        )

    @staticmethod
    def _extract_pytest_summary(lines: list[str]) -> tuple[int, int]:
        passed = 0
        failed = 0
        for line in lines:
            if " passed" not in line and " failed" not in line:
                continue
            lowered = line.lower().replace(",", " ").replace("=", " ")
            parts = lowered.split()
            for i, part in enumerate(parts):
                if part == "passed" and i > 0 and parts[i - 1].isdigit():
                    passed = int(parts[i - 1])
                if part == "failed" and i > 0 and parts[i - 1].isdigit():
                    failed = int(parts[i - 1])
        return passed, failed

    @staticmethod
    def _extract_pytest_failures(lines: list[str]) -> list[str]:
        failures: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("FAILED") or "AssertionError" in line:
                failures.append(stripped)
        return failures

    @staticmethod
    def _fallback_count_tests(lines: list[str]) -> tuple[int, int]:
        passed = 0
        failed = 0
        for line in lines:
            if "PASSED" in line:
                passed += 1
            elif "FAILED" in line:
                failed += 1
        return passed, failed

    def _parse_linter_output(self, exit_code: int, output: str) -> LintReport:
        """
        Parsuje output lintera do struktury LintReport.

        Args:
            exit_code: Kod wyjścia lintera
            output: Surowy output

        Returns:
            Obiekt LintReport
        """
        issues = []

        # Każda niepusta linia to potencjalny problem
        lines = output.split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("==="):
                issues.append(line)

        return LintReport(exit_code=exit_code, issues=issues, raw_output=output)

    def _format_test_report(self, report: TestReport) -> str:
        """
        Formatuje TestReport do czytelnego stringa.

        Args:
            report: Obiekt TestReport

        Returns:
            Sformatowany raport
        """
        if report.exit_code == 0:
            return f"✅ TESTY PRZESZŁY POMYŚLNIE\n\nPassed: {report.passed}\nFailed: {report.failed}\n"

        result = "❌ TESTY NIE PRZESZŁY\n\n"
        result += f"Exit Code: {report.exit_code}\n"
        result += f"Passed: {report.passed}\n"
        result += f"Failed: {report.failed}\n\n"

        if report.failures:
            result += "BŁĘDY:\n"
            for i, failure in enumerate(report.failures[:10], 1):  # Max 10 błędów
                result += f"{i}. {failure}\n"

        # Dodaj fragment surowego outputu dla kontekstu
        result += f"\n--- RAW OUTPUT (fragment) ---\n{report.raw_output[:500]}"

        return result

    def _format_lint_report(self, report: LintReport) -> str:
        """
        Formatuje LintReport do czytelnego stringa.

        Args:
            report: Obiekt LintReport

        Returns:
            Sformatowany raport
        """
        if report.exit_code == 0 and not report.issues:
            return "✅ LINTER: Brak problemów ze stylem kodu\n"

        result = f"⚠️ LINTER: Znaleziono {len(report.issues)} problemów\n\n"

        if report.issues:
            result += "PROBLEMY:\n"
            for i, issue in enumerate(report.issues[:20], 1):  # Max 20 problemów
                result += f"{i}. {issue}\n"

        return result
