"""Testy jednostkowe dla TestSkill."""

import tempfile
from pathlib import Path

import pytest

from venom_core.execution.skills.test_skill import TestSkill


@pytest.fixture
def test_skill():
    """Fixture dla TestSkill wymuszający ścieżkę lokalną (stabilne testy jednostkowe)."""
    yield TestSkill(habitat=None, allow_local_execution=True)


@pytest.mark.asyncio
async def test_run_pytest_with_no_tests(test_skill):
    """Test uruchomienia pytest gdy nie ma testów."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Uruchom pytest w pustym katalogu
        result = await test_skill.run_pytest(test_path=tmpdir)

    assert result is not None
    assert isinstance(result, str)
    # Może być 'no tests' lub exit code różny od 0
    assert "pytest" in result.lower() or "test" in result.lower()


@pytest.mark.asyncio
async def test_run_linter(test_skill):
    """Test uruchomienia lintera."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "sample.py"
        test_file.write_text("x=1\n", encoding="utf-8")
        result = await test_skill.run_linter(path=tmpdir)

    assert result is not None
    assert isinstance(result, str)
    # Linter powinien się uruchomić (nawet jeśli nie ma plików do sprawdzenia)


def test_parse_pytest_output_success():
    """Test parsowania pomyślnego outputu pytest."""
    test_skill = TestSkill()

    output = """
    ============================= test session starts ==============================
    collected 5 items

    tests/test_example.py::test_one PASSED                                   [ 20%]
    tests/test_example.py::test_two PASSED                                   [ 40%]
    tests/test_example.py::test_three PASSED                                 [ 60%]
    tests/test_example.py::test_four PASSED                                  [ 80%]
    tests/test_example.py::test_five PASSED                                  [100%]

    ============================== 5 passed in 0.05s ===============================
    """

    report = test_skill._parse_pytest_output(0, output)

    assert report.exit_code == 0
    assert report.passed == 5
    assert report.failed == 0
    assert len(report.failures) == 0


def test_parse_pytest_output_with_failures():
    """Test parsowania outputu pytest z błędami."""
    test_skill = TestSkill()

    output = """
    ============================= test session starts ==============================
    collected 3 items

    tests/test_example.py::test_one PASSED                                   [ 33%]
    tests/test_example.py::test_two FAILED                                   [ 66%]
    tests/test_example.py::test_three PASSED                                 [100%]

    =================================== FAILURES ===================================
    _________________________________ test_two _____________________________________

        def test_two():
    >       assert 1 == 2
    E       AssertionError: assert 1 == 2

    tests/test_example.py:10: AssertionError
    =========================== 2 passed, 1 failed in 0.10s ========================
    """

    report = test_skill._parse_pytest_output(1, output)

    assert report.exit_code == 1
    assert report.passed == 2
    assert report.failed == 1
    assert len(report.failures) > 0
    assert any("FAILED" in f or "AssertionError" in f for f in report.failures)


def test_parse_linter_output():
    """Test parsowania outputu lintera."""
    test_skill = TestSkill()

    output = """
    src/example.py:10:1: E302 expected 2 blank lines, found 1
    src/example.py:15:80: E501 line too long (92 > 79 characters)
    src/example.py:20:1: W391 blank line at end of file
    """

    report = test_skill._parse_linter_output(1, output)

    assert report.exit_code == 1
    assert len(report.issues) == 3
    assert "E302" in report.issues[0]
    assert "E501" in report.issues[1]


def test_format_test_report_success():
    """Test formatowania raportu sukcesu."""
    test_skill = TestSkill()

    from venom_core.execution.skills.test_skill import TestReport

    report = TestReport(
        exit_code=0, passed=5, failed=0, failures=[], raw_output="All tests passed"
    )

    result = test_skill._format_test_report(report)

    assert "PRZESZŁY POMYŚLNIE" in result
    assert "Passed: 5" in result
    assert "Failed: 0" in result


def test_format_test_report_failure():
    """Test formatowania raportu z błędami."""
    test_skill = TestSkill()

    from venom_core.execution.skills.test_skill import TestReport

    report = TestReport(
        exit_code=1,
        passed=2,
        failed=1,
        failures=["FAILED tests/test_example.py::test_two - AssertionError"],
        raw_output="Some tests failed",
    )

    result = test_skill._format_test_report(report)

    assert "NIE PRZESZŁY" in result
    assert "Exit Code: 1" in result
    assert "Passed: 2" in result
    assert "Failed: 1" in result
    assert "BŁĘDY:" in result
    assert "AssertionError" in result


def test_extract_pytest_summary_handles_mixed_tokens():
    test_skill = TestSkill()
    lines = ["=== 12 passed, 3 failed, 2 warnings in 1.23s ==="]

    passed, failed = test_skill._extract_pytest_summary(lines)

    assert passed == 12
    assert failed == 3


def test_parse_pytest_output_uses_fallback_counts():
    test_skill = TestSkill()
    output = """
tests/a.py::test_ok PASSED
tests/a.py::test_bad FAILED
"""

    report = test_skill._parse_pytest_output(1, output)
    assert report.passed == 1
    assert report.failed == 1


@pytest.mark.asyncio
async def test_run_linter_with_disabled_local_and_missing_docker_returns_warning():
    skill = TestSkill(allow_local_execution=False)
    skill.docker_available = False
    skill.habitat = None

    result = await skill.run_linter(path=".")
    assert "Docker sandbox jest niedostępny" in result


def test_is_valid_lint_path_accepts_and_rejects_values():
    assert TestSkill._is_valid_lint_path("tests/test_example.py") is True
    assert TestSkill._is_valid_lint_path("bad path with spaces") is False
