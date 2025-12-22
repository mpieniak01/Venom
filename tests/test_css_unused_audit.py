import json
import subprocess
import sys
from pathlib import Path


def test_css_unused_audit_runs():
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "css_unused_audit.py"
    result = subprocess.run(
        [sys.executable, str(script), "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    assert "files" in data
    assert "summary" in data
