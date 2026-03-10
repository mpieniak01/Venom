from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _run_env_contract(
    script: Path, snippet: str, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", "-lc", f'set -euo pipefail\nsource "{script}"\n{snippet}\n'],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_env_contract_get_precedence(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "lib" / "env_contract.sh"
    env_file = tmp_path / ".env.dev"
    env_file.write_text("TEST_KEY=file-value\n", encoding="utf-8")

    from_env = _run_env_contract(
        script,
        f'printf "%s" "$(env_contract_get TEST_KEY default-value "{env_file}")"',
        {"TEST_KEY": "env-value"},
    )
    assert from_env.returncode == 0, from_env.stderr
    assert from_env.stdout == "env-value"

    from_file = _run_env_contract(
        script,
        f'unset TEST_KEY\nprintf "%s" "$(env_contract_get TEST_KEY default-value "{env_file}")"',
    )
    assert from_file.returncode == 0, from_file.stderr
    assert from_file.stdout == "file-value"

    from_default = _run_env_contract(
        script,
        f'printf "%s" "$(env_contract_get MISSING_KEY default-value "{env_file}")"',
    )
    assert from_default.returncode == 0, from_default.stderr
    assert from_default.stdout == "default-value"


def test_env_contract_origin_reports_source(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "lib" / "env_contract.sh"
    env_file = tmp_path / ".env.dev"
    env_file.write_text("ORIGIN_KEY=file-source\n", encoding="utf-8")

    from_env = _run_env_contract(
        script,
        f'printf "%s" "$(env_contract_origin ORIGIN_KEY "{env_file}" "fallback")"',
        {"ORIGIN_KEY": "env-source"},
    )
    assert from_env.returncode == 0, from_env.stderr
    assert from_env.stdout == "env"

    from_file = _run_env_contract(
        script,
        f'unset ORIGIN_KEY\nprintf "%s" "$(env_contract_origin ORIGIN_KEY "{env_file}" "fallback")"',
    )
    assert from_file.returncode == 0, from_file.stderr
    assert from_file.stdout == "file"

    from_default = _run_env_contract(
        script,
        f'printf "%s" "$(env_contract_origin MISSING_ORIGIN "{env_file}" "fallback")"',
    )
    assert from_default.returncode == 0, from_default.stderr
    assert from_default.stdout == "default"


def test_env_contract_resolve_file_paths(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "lib" / "env_contract.sh"
    root_dir = tmp_path / "repo"
    root_dir.mkdir(parents=True)

    resolved = _run_env_contract(
        script,
        f'echo "$(env_contract_resolve_file ".env.dev" "{root_dir}")"\n'
        f'echo "$(env_contract_resolve_file "/tmp/absolute.env" "{root_dir}")"',
    )
    assert resolved.returncode == 0, resolved.stderr
    lines = resolved.stdout.strip().splitlines()
    assert lines[0] == f"{root_dir}/.env.dev"
    assert lines[1] == "/tmp/absolute.env"
