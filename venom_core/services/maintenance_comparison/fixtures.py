"""Small injected faults: gold code and adjudication stay outside model copies.

These are synthetic maintenance cases, not historical production Venom bugs.
Localization cases use the real pinned Venom tree separately.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RepairFixture:
    id: str
    broken: str
    gold: str
    oracle: str
    visible_test: str


def repairs() -> list[RepairFixture]:
    """Eight independently checkable faults, including one regression-test task."""
    rows = [
        (
            "01",
            "def total(values):\n    return sum(value for value in vals)\n",
            "def total(values):\n    return sum(values)\n",
            "assert total([2, 3]) == 5\nassert total([]) == 0",
            "assert total([1]) == 1",
        ),
        (
            "02",
            "def mean(values):\n    return sum(values) / len(values)\n",
            "def mean(values):\n    return sum(values) / len(values) if values else None\n",
            "assert mean([]) is None\nassert mean([2, 4]) == 3",
            "assert mean([2, 4]) == 3",
        ),
        (
            "03",
            "import missing_venom_dependency\ndef enabled(value):\n    return bool(value)\n",
            "def enabled(value):\n    return bool(value)\n",
            "assert enabled(True) is True\nassert enabled(False) is False",
            "assert enabled(True)",
        ),
        (
            "04",
            "from pathlib import NonexistentPath\ndef suffix(value):\n    return value.rsplit('.', 1)[-1]\n",
            "def suffix(value):\n    return value.rsplit('.', 1)[-1]\n",
            "assert suffix('a.py') == 'py'\nassert suffix('a.txt') == 'txt'",
            "assert suffix('a.py') == 'py'",
        ),
        (
            "05",
            "def query(client):\n    return client.get()['state']\n",
            "def query(client):\n    return client.get()['state']\n",
            "from types import SimpleNamespace\nassert query(SimpleNamespace(get=lambda: {'state': 'ready'})) == 'ready'",
            "from types import SimpleNamespace\nassert query(SimpleNamespace(get=lambda: 'ready')) == 'ready'",
        ),
        (
            "06",
            "def budget(value, limit=8):\n    return max(value, limit)\n",
            "def budget(value, limit=8):\n    return min(value, limit)\n",
            "assert budget(3) == 3\nassert budget(12) == 8\nassert budget(12, limit=4) == 4",
            "assert budget(12) == 8",
        ),
        (
            "07",
            "def normalize(value):\n    return value.strip()\n",
            "def normalize(value):\n    return value.strip() if value is not None else ''\n",
            "assert normalize(None) == ''\nassert normalize(' x ') == 'x'",
            "assert normalize(' x ') == 'x'",
        ),
        (
            "09",
            "def unique(values):\n    return list(set(values))\n",
            "def unique(values):\n    return list(dict.fromkeys(values))\n",
            "assert unique([3, 1, 3, 2]) == [3, 1, 2]\nassert unique([]) == []",
            "assert len(unique([1, 1, 2])) == 2",
        ),
    ]
    return [RepairFixture(*row) for row in rows]


def _visible_test(source: str) -> str:
    lines = source.splitlines()
    imports = [line for line in lines if line.startswith(("from ", "import "))]
    body = [line for line in lines if not line.startswith(("from ", "import "))]
    return (
        "from maintenance_fixture import *\n"
        + "\n".join(imports)
        + "\n\ndef test_contract():\n"
        + "\n".join("    " + line for line in body)
        + "\n"
    )


def visible_files(case: RepairFixture) -> dict[str, str]:
    return {
        "maintenance_fixture.py": case.broken,
        "test_visible.py": _visible_test(case.visible_test),
    }


def gold_files(case: RepairFixture) -> dict[str, str]:
    files = visible_files(case)
    files["maintenance_fixture.py"] = case.gold
    if case.id == "05":
        files["test_visible.py"] = _visible_test(
            case.visible_test.replace("lambda: 'ready'", "lambda: {'state': 'ready'}")
        )
    if case.id == "07":
        files["test_regression.py"] = (
            "from maintenance_fixture import normalize\ndef test_none_regression():\n    assert normalize(None) == ''\n"
        )
    return files
