from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_env_report_diff_generates_markdown(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "env_report_diff.py"

    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    out = tmp_path / "diff.md"

    before.write_text(
        json.dumps(
            {
                "artifacts": {
                    "directories": [
                        {"path": "web-next/node_modules", "size_bytes": 1000},
                        {"path": ".pytest_cache", "size_bytes": 100},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    after.write_text(
        json.dumps(
            {
                "artifacts": {
                    "directories": [
                        {"path": "web-next/node_modules", "size_bytes": 400},
                        {"path": ".pytest_cache", "size_bytes": 0},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--before",
            str(before),
            "--after",
            str(after),
            "--output",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "Env Audit Diff" in text
    assert "web-next/node_modules" in text
