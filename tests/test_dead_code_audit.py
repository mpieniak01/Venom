from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "dev" / "dead_code_audit.py"
    spec = importlib.util.spec_from_file_location("dead_code_audit", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_extract_vulture_symbol_from_message():
    module = _load_module()
    symbol = module._extract_vulture_symbol("unused function '_foo' (90% confidence)")
    assert symbol == "_foo"


def test_is_vulture_allowlisted_by_symbol_and_line():
    module = _load_module()
    allowlist = {"venom_core/x.py:_keep", "venom_core/x.py:12"}
    assert module._is_vulture_allowlisted(
        file_path="venom_core/x.py",
        line=3,
        symbol="_keep",
        allowlist=allowlist,
    )
    assert module._is_vulture_allowlisted(
        file_path="venom_core/x.py",
        line=12,
        symbol="_other",
        allowlist=allowlist,
    )
    assert not module._is_vulture_allowlisted(
        file_path="venom_core/x.py",
        line=4,
        symbol="_drop",
        allowlist=allowlist,
    )


def test_cli_with_vulture_fake_runner_json(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "dead_code_audit.py"

    (tmp_path / "venom_core").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "venom_core" / "x.py").write_text(
        "def _x():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "config" / "dead_code_allowlist.txt").write_text("", encoding="utf-8")
    (tmp_path / "config" / "dead_code_vulture_allowlist.txt").write_text(
        "venom_core/x.py:_keep\n", encoding="utf-8"
    )

    fake_vulture = tmp_path / "fake-vulture.sh"
    fake_vulture.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"venom_core/x.py:10: unused function '_keep' (80% confidence)\"\n"
        "echo \"venom_core/x.py:11: unused function '_drop' (90% confidence)\"\n",
        encoding="utf-8",
    )
    fake_vulture.chmod(fake_vulture.stat().st_mode | stat.S_IXUSR)

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--paths",
            "venom_core",
            "--format",
            "json",
            "--with-vulture",
            "--vulture-bin",
            str(fake_vulture),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["vulture"]["enabled"] is True
    assert payload["vulture"]["available"] is True
    assert payload["summary"]["findings_vulture_unused_symbol"] == 1
    vulture_findings = [
        item
        for item in payload["findings"]
        if item.get("type") == "vulture_unused_symbol"
    ]
    assert len(vulture_findings) == 1
    assert vulture_findings[0]["symbol"] == "_drop"


def test_cli_with_vulture_missing_binary_reports_unavailable(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "dead_code_audit.py"

    (tmp_path / "venom_core").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "venom_core" / "x.py").write_text(
        "def _x():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "config" / "dead_code_allowlist.txt").write_text("", encoding="utf-8")
    (tmp_path / "config" / "dead_code_vulture_allowlist.txt").write_text(
        "", encoding="utf-8"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--paths",
            "venom_core",
            "--format",
            "json",
            "--with-vulture",
            "--vulture-bin",
            "/definitely-missing-vulture-binary",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["vulture"]["enabled"] is True
    assert payload["vulture"]["available"] is False
