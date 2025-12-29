import os
import shutil
import subprocess
from pathlib import Path

import pytest

TSX_PATH = Path("web-next/node_modules/.bin/tsx")


def _format_with_tsx(content: str) -> str:
    if not shutil.which("node") or not TSX_PATH.exists():
        pytest.skip("Node/tsx not available; skip frontend formatting checks.")
    env = os.environ.copy()
    env["COMPUTE_INPUT"] = content
    result = subprocess.run(
        [
            str(TSX_PATH),
            "-e",
            (
                "import { formatComputationContent } "
                "from './web-next/lib/markdown-format.ts';"
                "console.log(formatComputationContent(process.env.COMPUTE_INPUT ?? ''));"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout.strip()


def test_format_table_from_2d_list():
    output = _format_with_tsx("[[1,2],[3,4]]")
    assert "| Col 1 | Col 2 |" in output
    assert "| 1 | 2 |" in output
    assert "| 3 | 4 |" in output


def test_format_list_as_bullets():
    output = _format_with_tsx("[1,2,3]")
    assert "- 1" in output
    assert "- 2" in output
    assert "- 3" in output


def test_format_dict_as_table():
    output = _format_with_tsx('{"a": 1, "b": 2}')
    assert "| a | b |" in output
    assert "| 1 | 2 |" in output


def test_natural_text_unchanged():
    content = "To jest zwykly tekst bez JSON."
    output = _format_with_tsx(content)
    assert output == content


def test_code_fence_json_replaced_in_message():
    content = "Wynik:\n```json\n[[1,2],[3,4]]\n```\nKoniec."
    output = _format_with_tsx(content)
    assert "Wynik:" in output
    assert "Koniec." in output
    assert "| Col 1 | Col 2 |" in output
