"""Moduł: test_skill - wrapper na narzędzia testowe w DockerHabitat."""

from dataclasses import dataclass
from typing import Annotated, List

from semantic_kernel.functions import kernel_function

from venom_core.infrastructure.docker_habitat import DockerHabitat
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TestReport:
    """Raport z wykonania testów pytest."""

    exit_code: int
    passed: int
    failed: int
    failures: List[str]  # Szczegóły błędów
    raw_output: str  # Surowy output dla dodatkowej analizy


@dataclass
class LintReport:
    """Raport z wykonania lintera."""

    exit_code: int
    issues: List[str]  # Lista problemów znalezionych przez linter
    raw_output: str


class TestSkill:
    """
    Skill do uruchamiania testów i lintera w izolowanym środowisku Docker.

    Używa DockerHabitat do bezpiecznego wykonywania komend testowych.
    NIE uruchamia testów lokalnie - wszystko w kontenerze.
    """

    def __init__(self, habitat: DockerHabitat = None):
        """
        Inicjalizacja TestSkill.

        Args:
            habitat: Instancja DockerHabitat (jeśli None, zostanie utworzona)
        """
        self.habitat = habitat or DockerHabitat()
        logger.info("TestSkill zainicjalizowany")

    @kernel_function(
        name="run_pytest",
        description="Uruchamia testy pytest w kontenerze Docker i parsuje wyniki.",
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
            logger.info(f"Uruchamiam pytest dla: {test_path}")

            # Walidacja test_path - zapobieganie command injection
            import re

            if not re.match(r"^[a-zA-Z0-9_./\-]+$", test_path):
                return f"❌ Błąd: Nieprawidłowa ścieżka testów: {test_path}"

            # Przygotuj komendę pytest z odpowiednimi flagami
            # Używamy shlex.quote dla bezpieczeństwa
            import shlex

            safe_path = shlex.quote(test_path)
            command = f"python -m pytest {safe_path} -v --tb=short --color=no"

            # Wykonaj w kontenerze
            exit_code, output = self.habitat.execute(command, timeout=timeout)

            # Sparsuj wyniki
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
        description="Uruchamia linter (ruff) w kontenerze Docker.",
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
            logger.info(f"Uruchamiam linter dla: {path}")

            # Walidacja path - zapobieganie command injection
            import re

            if not re.match(r"^[a-zA-Z0-9_./\-]+$", path):
                return f"❌ Błąd: Nieprawidłowa ścieżka: {path}"

            # Używamy shlex.quote dla bezpieczeństwa
            import shlex

            safe_path = shlex.quote(path)

            # Spróbuj najpierw ruff, jeśli nie ma, użyj flake8
            command = (
                f"python -m ruff check {safe_path} || python -m flake8 {safe_path}"
            )

            # Wykonaj w kontenerze
            exit_code, output = self.habitat.execute(command, timeout=timeout)

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

    def _parse_pytest_output(self, exit_code: int, output: str) -> TestReport:
        """
        Parsuje output pytest do struktury TestReport.

        Args:
            exit_code: Kod wyjścia pytest
            output: Surowy output

        Returns:
            Obiekt TestReport
        """
        passed = 0
        failed = 0
        failures = []

        # Parsuj linię z podsumowaniem (np. "5 passed, 2 failed in 1.23s")
        lines = output.split("\n")

        for line in lines:
            # Szukaj linii z podsumowaniem
            if " passed" in line or " failed" in line:
                # Wyciągnij liczby
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "passed" and i > 0:
                        try:
                            passed = int(parts[i - 1])
                        except (ValueError, IndexError):
                            pass
                    elif part == "failed" and i > 0:
                        try:
                            failed = int(parts[i - 1])
                        except (ValueError, IndexError):
                            pass

            # Zbierz szczegóły błędów (linie z FAILED)
            if line.strip().startswith("FAILED") or "AssertionError" in line:
                failures.append(line.strip())

        # Jeśli nie znaleziono podsumowania, spróbuj alternatywnej metody
        if passed == 0 and failed == 0 and exit_code != 0:
            # Sprawdź czy są jakieś linie z PASSED/FAILED
            for line in lines:
                if "PASSED" in line:
                    passed += 1
                elif "FAILED" in line:
                    failed += 1

        return TestReport(
            exit_code=exit_code,
            passed=passed,
            failed=failed,
            failures=failures,
            raw_output=output,
        )

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
