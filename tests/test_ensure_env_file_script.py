from __future__ import annotations

import subprocess
from pathlib import Path


def _run(
    script: Path, env_file: Path, example_file: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), str(env_file), str(example_file)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_ensure_env_file_copies_example_when_missing(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "ensure_env_file.sh"
    env_file = tmp_path / ".env.test"
    example_file = tmp_path / ".env.test.example"
    example_file.write_text("A=1\nB=2\n", encoding="utf-8")

    result = _run(script, env_file, example_file)

    assert result.returncode == 0, result.stderr
    assert env_file.exists()
    assert env_file.read_text(encoding="utf-8") == "A=1\nB=2\n"
    assert "Utworzono" in result.stdout


def test_ensure_env_file_keeps_existing_file_unchanged(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "ensure_env_file.sh"
    env_file = tmp_path / ".env.test"
    example_file = tmp_path / ".env.test.example"
    env_file.write_text("X=9\n", encoding="utf-8")
    example_file.write_text("X=0\n", encoding="utf-8")

    result = _run(script, env_file, example_file)

    assert result.returncode == 0, result.stderr
    assert env_file.read_text(encoding="utf-8") == "X=9\n"
    assert result.stdout.strip() == ""


def test_ensure_env_file_warns_when_both_missing(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "ensure_env_file.sh"
    env_file = tmp_path / ".env.test"
    example_file = tmp_path / ".env.test.example"

    result = _run(script, env_file, example_file)

    assert result.returncode == 0, result.stderr
    assert not env_file.exists()
    assert "Brak" in result.stdout
