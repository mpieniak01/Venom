#!/usr/bin/env python3
"""Definicje zadań benchmarkowych (Python coding + debug loop)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskSpec:
    """Kontrakt zadania benchmarkowego."""

    task_id: str
    title: str
    difficulty: str
    description: str
    required_files: tuple[str, ...]
    starter_files: dict[str, str]
    tests: dict[str, str]


_SIMPLE_SOLUTION_TEMPLATE = (
    "Napisz plik `solution.py` zawierający funkcję `normalize_records(records: list[dict]) -> list[dict]` "
    "która: "
    "1) odrzuca rekordy bez klucza `id` lub `value`, "
    "2) normalizuje `id` do lowercase string, "
    "3) mapuje `value` do int, "
    "4) usuwa duplikaty po `id` zachowując rekord z największym `value`, "
    "5) zwraca rekordy posortowane rosnąco po `id`."
)

_SANITY_SOLUTION_TEMPLATE = (
    "Napisz plik `solution.py` zawierający funkcję "
    "`safe_divide(a: float, b: float) -> float | None`. "
    "Funkcja ma zwracać `a / b`, a gdy `b == 0` ma zwracać `None`. "
    "Zachowaj poprawną składnię Python i prostą implementację."
)

_COMPLEX_SOLUTION_TEMPLATE = (
    "Napisz dwa pliki: `validators.py` i `pipeline.py`. "
    "W `validators.py` zaimplementuj `parse_line(line: str) -> tuple[str, int]` dla formatu `team,points`. "
    "W `pipeline.py` zaimplementuj `build_scoreboard(lines: list[str]) -> list[tuple[str, int]]` które: "
    "1) wykorzystuje `parse_line`, "
    "2) agreguje punkty per team, "
    "3) pomija puste linie, "
    "4) rzuca `ValueError` dla niepoprawnego formatu, "
    "5) zwraca listę krotek sortowaną malejąco po punktach, a przy remisie alfabetycznie."
)

BUGGY_VALIDATORS = '''"""Validation helpers for scoreboard parsing."""


def parse_line(line: str) -> tuple[str, int]:
    raw = line.strip()
    if not raw:
        raise ValueError("empty line")
    # BUG: invalid points are not validated with dedicated error handling.
    team, points = raw.split(",", 1)
    team = team.strip().lower()
    if not team:
        raise ValueError("missing team")
    return team, int(points)
'''

BUGGY_PIPELINE = '''"""Scoreboard builder."""

from validators import parse_line


def build_scoreboard(lines: list[str]) -> list[tuple[str, int]]:
    totals: dict[str, int] = {}
    for line in lines:
        if line.strip() == "":
            continue
        team, points = parse_line(line)
        # BUG: should aggregate with + points
        totals[team] = points
    return sorted(totals.items(), key=lambda item: (-item[1], item[0]))
'''

SANITY_TESTS = {
    "test_solution.py": """from solution import safe_divide


def test_safe_divide_happy_path():
    assert safe_divide(10, 2) == 5
    assert safe_divide(9, 3) == 3


def test_safe_divide_zero_returns_none():
    assert safe_divide(10, 0) is None


def test_safe_divide_float_values():
    assert safe_divide(1.5, 0.5) == 3.0
""",
}

SIMPLE_TESTS = {
    "test_solution.py": """from solution import normalize_records


def test_normalize_records_happy_path():
    data = [
        {"id": "A", "value": "10"},
        {"id": "b", "value": 7},
        {"id": "a", "value": 12},
        {"id": "c", "value": "3"},
    ]
    assert normalize_records(data) == [
        {"id": "a", "value": 12},
        {"id": "b", "value": 7},
        {"id": "c", "value": 3},
    ]


def test_normalize_records_drop_invalid_and_empty():
    data = [
        {},
        {"id": "x"},
        {"value": 1},
        {"id": "", "value": 1},
        {"id": "ok", "value": "4"},
    ]
    assert normalize_records(data) == [{"id": "ok", "value": 4}]


def test_normalize_records_raises_for_non_integer_value():
    data = [{"id": "a", "value": "x"}]
    try:
        normalize_records(data)
    except ValueError:
        assert True
    else:
        raise AssertionError("expected ValueError")
""",
}

COMPLEX_TESTS = {
    "test_scoreboard.py": """import pytest

from pipeline import build_scoreboard
from validators import parse_line


def test_parse_line_and_build_scoreboard():
    lines = ["red,3", "blue,4", "red,2", "blue,1", "green,7"]
    assert build_scoreboard(lines) == [("green", 7), ("blue", 5), ("red", 5)]


def test_sort_tie_alphabetical():
    lines = ["zeta,5", "alpha,5"]
    assert build_scoreboard(lines) == [("alpha", 5), ("zeta", 5)]


def test_invalid_format_raises():
    with pytest.raises(ValueError):
        parse_line("broken-line")


def test_invalid_points_raises():
    with pytest.raises(ValueError):
        parse_line("team,not-int")


def test_extra_commas_raise():
    with pytest.raises(ValueError):
        parse_line("team,1,2")
""",
}

TASKS: dict[str, TaskSpec] = {
    "python_sanity": TaskSpec(
        task_id="python_sanity",
        title="Python coding - sanity",
        difficulty="sanity",
        description=_SANITY_SOLUTION_TEMPLATE,
        required_files=("solution.py",),
        starter_files={},
        tests=SANITY_TESTS,
    ),
    "python_simple": TaskSpec(
        task_id="python_simple",
        title="Python coding - simple",
        difficulty="simple",
        description=_SIMPLE_SOLUTION_TEMPLATE,
        required_files=("solution.py",),
        starter_files={},
        tests=SIMPLE_TESTS,
    ),
    "python_complex": TaskSpec(
        task_id="python_complex",
        title="Python coding - complex",
        difficulty="complex",
        description=_COMPLEX_SOLUTION_TEMPLATE,
        required_files=("validators.py", "pipeline.py"),
        starter_files={},
        tests=COMPLEX_TESTS,
    ),
    "python_complex_bugfix": TaskSpec(
        task_id="python_complex_bugfix",
        title="Python coding - complex bugfix",
        difficulty="complex",
        description=(
            "Napraw istniejące pliki `validators.py` i `pipeline.py` tak, aby wszystkie testy przechodziły. "
            "Nie zmieniaj testów."
        ),
        required_files=("validators.py", "pipeline.py"),
        starter_files={
            "validators.py": BUGGY_VALIDATORS,
            "pipeline.py": BUGGY_PIPELINE,
        },
        tests=COMPLEX_TESTS,
    ),
}


def get_task(task_id: str) -> TaskSpec:
    """Zwraca specyfikację zadania lub rzuca KeyError."""
    return TASKS[task_id]


def list_tasks() -> list[str]:
    """Lista dostępnych identyfikatorów zadań."""
    return sorted(TASKS.keys())


def build_prompt(task: TaskSpec) -> str:
    """Buduje prompt generacji/naprawy z twardym kontraktem JSON."""
    required = ", ".join(task.required_files)
    starter_section = ""
    if task.starter_files:
        chunks: list[str] = []
        for path, content in task.starter_files.items():
            chunks.append(f"FILE: {path}\n```python\n{content}\n```")
        starter_section = "\nAktualne pliki (do poprawy):\n" + "\n\n".join(chunks)

    return (
        "Jesteś ekspertem Python. "
        "Zwróć WYŁĄCZNIE poprawny JSON bez dodatkowego tekstu. "
        'Schema: {"files": {"path.py": "<content>"}, "notes": "short"}. '
        f"Wymagane pliki: {required}. "
        "Nie dodawaj ścieżek absolutnych ani katalogów nadrzędnych. "
        f"Zadanie: {task.description}."
        f"{starter_section}"
    )


def build_feedback_prompt(
    task: TaskSpec, check_output: str, current_files: dict[str, str]
) -> str:
    """Buduje prompt iteracyjny po nieudanym teście."""
    files_block = "\n\n".join(
        f"FILE: {path}\n```python\n{content}\n```"
        for path, content in current_files.items()
    )
    return (
        "Popraw kod tak, aby testy i ruff przechodziły. "
        'Zwróć WYŁĄCZNIE JSON w tym samym schemacie: {"files": {...}, "notes": "..."}. '
        "Oddaj pełne treści plików wymaganych przez zadanie. "
        f"Wymagane pliki: {', '.join(task.required_files)}.\n"
        f"Kontekst zadania: {task.description}\n"
        "Aktualne pliki:\n"
        f"{files_block}\n\n"
        "Raport runnera:\n"
        f"{check_output}"
    )
