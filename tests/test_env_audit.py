from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_env_audit_generates_json_and_markdown(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "env_audit.py"

    _write(
        tmp_path / "requirements.txt",
        "fastapi==0.128.0\ntransformers>=4.57.6\npytest==9.0.2\n",
    )
    _write(
        tmp_path / "requirements-ci-lite.txt",
        "fastapi==0.128.0\npytest==9.0.2\n",
    )

    _write(
        tmp_path / "web-next" / "package.json",
        json.dumps(
            {
                "name": "web-next",
                "dependencies": {"react": "19.1.0", "clsx": "^2.1.1"},
                "devDependencies": {"typescript": "^5"},
            }
        ),
    )
    _write(
        tmp_path / "web-next" / "package-lock.json",
        json.dumps(
            {
                "name": "web-next",
                "lockfileVersion": 3,
                "packages": {
                    "": {
                        "dependencies": {"react": "19.1.0", "clsx": "^2.1.1"},
                        "devDependencies": {"typescript": "^5"},
                    },
                    "node_modules/react": {"version": "19.1.0"},
                    "node_modules/clsx": {"version": "2.1.1"},
                    "node_modules/pkg-a": {"version": "1.0.0"},
                    "node_modules/x/node_modules/pkg-a": {"version": "2.0.0"},
                },
            }
        ),
    )
    _write(tmp_path / "web-next" / "app" / "x.tsx", "import { clsx } from 'clsx'\n")
    _write(tmp_path / ".pytest_cache" / "state", "x")

    out_json = tmp_path / "logs" / "audit.json"
    out_md = tmp_path / "logs" / "audit.md"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--output-json",
            str(out_json),
            "--output-md",
            str(out_md),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert out_json.exists()
    assert out_md.exists()

    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert "artifacts" in data
    assert "dependencies" in data
    assert "docker" in data
    assert "classification" in data["dependencies"]["python"]
    assert any(
        x["package"] == "transformers"
        for x in data["dependencies"]["python"]["classification"]["optional-heavy"]
    )


def test_env_audit_ci_check_fails_for_critical_pin_mismatch(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "env_audit.py"

    _write(tmp_path / "requirements.txt", "fastapi==0.128.0\n")
    _write(tmp_path / "requirements-ci-lite.txt", "fastapi==0.127.0\n")
    _write(
        tmp_path / "web-next" / "package.json",
        json.dumps({"name": "web-next", "dependencies": {}, "devDependencies": {}}),
    )
    _write(
        tmp_path / "web-next" / "package-lock.json",
        json.dumps({"name": "web-next", "lockfileVersion": 3, "packages": {"": {}}}),
    )

    result = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path), "--ci-check"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "critical pin mismatch" in result.stdout


def test_env_audit_ci_check_accepts_compatible_range_and_pin(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "dev" / "env_audit.py"

    _write(tmp_path / "requirements.txt", "fastapi>=0.128.0\n")
    _write(tmp_path / "requirements-ci-lite.txt", "fastapi==0.128.0\n")
    _write(
        tmp_path / "web-next" / "package.json",
        json.dumps({"name": "web-next", "dependencies": {}, "devDependencies": {}}),
    )
    _write(
        tmp_path / "web-next" / "package-lock.json",
        json.dumps({"name": "web-next", "lockfileVersion": 3, "packages": {"": {}}}),
    )

    result = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path), "--ci-check"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Dependency policy check passed" in result.stdout
