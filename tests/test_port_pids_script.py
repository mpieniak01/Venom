from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _run_script(
    script: Path, mock_bin: Path, *args: str
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return subprocess.run(
        ["bash", str(script), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_port_pids_rejects_invalid_port() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "port_pids.sh"

    result = subprocess.run(
        ["bash", str(script), "abc"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Invalid port" in result.stderr


def test_port_pids_uses_lsof_when_available(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "port_pids.sh"
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir(parents=True)

    _write_executable(
        mock_bin / "lsof",
        "#!/usr/bin/env bash\necho 123\necho 456\n",
    )

    result = _run_script(script, mock_bin, "3000")

    assert result.returncode == 0
    assert result.stdout.strip().splitlines() == ["123", "456"]


def test_port_pids_falls_back_to_fuser_then_ss(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "port_pids.sh"
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir(parents=True)

    _write_executable(mock_bin / "lsof", "#!/usr/bin/env bash\nexit 1\n")
    _write_executable(
        mock_bin / "fuser",
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == "-n" && "$2" == "tcp" && "$3" == "3000" ]]; then\n'
        '  echo "3000/tcp: 321 654"\n'
        "fi\n",
    )
    _write_executable(
        mock_bin / "ss",
        "#!/usr/bin/env bash\n"
        "cat <<'EOF'\n"
        'LISTEN 0 128 0.0.0.0:4000 0.0.0.0:* users:(("node",pid=777,fd=20),("node",pid=888,fd=21))\n'
        "EOF\n",
    )

    result_fuser = _run_script(script, mock_bin, "3000")
    assert result_fuser.returncode == 0
    assert result_fuser.stdout.strip().splitlines() == ["321", "654"]

    _write_executable(mock_bin / "fuser", "#!/usr/bin/env bash\nexit 1\n")
    result_ss = _run_script(script, mock_bin, "4000")
    assert result_ss.returncode == 0
    assert result_ss.stdout.strip().splitlines() == ["777", "888"]
