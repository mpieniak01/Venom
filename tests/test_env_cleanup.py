from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _make_dir_with_file(root: Path, rel: str) -> None:
    p = root / rel
    p.mkdir(parents=True, exist_ok=True)
    (p / "x.txt").write_text("x", encoding="utf-8")


def test_env_cleanup_safe_and_deep(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "env_cleanup.sh"

    _make_dir_with_file(tmp_path, ".pytest_cache")
    _make_dir_with_file(tmp_path, "web-next/.next")
    _make_dir_with_file(tmp_path, "web-next/node_modules")
    _make_dir_with_file(tmp_path, "models")

    env = os.environ.copy()
    env["ROOT_DIR"] = str(tmp_path)

    safe = subprocess.run(
        ["bash", str(script), "safe"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert safe.returncode == 0, safe.stderr
    assert not (tmp_path / ".pytest_cache").exists()
    assert not (tmp_path / "web-next/.next").exists()
    assert (tmp_path / "web-next/node_modules").exists()
    assert (tmp_path / "models").exists()

    deep_without_confirm = subprocess.run(
        ["bash", str(script), "deep"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert deep_without_confirm.returncode == 1

    env["CONFIRM_DEEP_CLEAN"] = "1"
    deep = subprocess.run(
        ["bash", str(script), "deep"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert deep.returncode == 0, deep.stderr
    assert not (tmp_path / "web-next/node_modules").exists()
    assert (tmp_path / "models").exists()
