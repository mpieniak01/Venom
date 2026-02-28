from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


def _run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_preprod_backup_and_verify_roundtrip(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "preprod" / "backup_restore.sh"

    env = os.environ.copy()
    env["ENVIRONMENT_ROLE"] = "preprod"
    env["ALLOW_DATA_MUTATION"] = "0"

    backup = _run(["bash", str(script), "backup"], cwd=tmp_path, env=env)
    assert backup.returncode == 0, backup.stderr
    match = re.search(r"Backup timestamp:\s*(\S+)", backup.stdout)
    assert match is not None
    ts = match.group(1)

    archive = tmp_path / "backups" / "preprod" / f"preprod-files-{ts}.tar.gz"
    checksum = tmp_path / "backups" / "preprod" / f"preprod-files-{ts}.tar.gz.sha256"
    assert archive.exists()
    assert checksum.exists()

    verify = _run(["bash", str(script), "verify", ts], cwd=tmp_path, env=env)
    assert verify.returncode == 0, verify.stderr
    assert "Archiwum plików zweryfikowane" in verify.stdout


def test_preprod_restore_requires_mutation_override(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "preprod" / "backup_restore.sh"

    env = os.environ.copy()
    env["ENVIRONMENT_ROLE"] = "preprod"
    env["ALLOW_DATA_MUTATION"] = "0"

    restore = _run(
        ["bash", str(script), "restore", "20260228-000000"], cwd=tmp_path, env=env
    )
    assert restore.returncode == 1
    assert "ALLOW_DATA_MUTATION=1" in restore.stdout


def test_preprod_audit_log_script_writes_json_line(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "preprod" / "audit_log.sh"
    log_path = tmp_path / "logs" / "preprod_audit.log"

    env = os.environ.copy()
    env["AUDIT_LOG"] = str(log_path)

    result = _run(
        ["bash", str(script), "codex", "backup", "task-177", "OK"],
        cwd=tmp_path,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert log_path.exists()

    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert payload["actor"] == "codex"
    assert payload["action"] == "backup"
    assert payload["ticket"] == "task-177"
    assert payload["result"] == "OK"
    assert payload["ts"].endswith("Z")
