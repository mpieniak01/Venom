"""Launcher routing contracts without starting API, UI or model processes."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("port", [8000, 8800, 9911])
def test_make_proxy_fallback_tracks_actual_backend_port(port):
    recipe = (
        ".PHONY: http-lan-test-value\n"
        "http-lan-test-value:\n"
        "\t@printf '%s\\n' '$(WEB_API_PROXY_TARGET)'\n"
    )
    env = dict(os.environ)
    for key in ("API_PROXY_TARGET", "WEB_API_PROXY_TARGET", "MAKEFLAGS"):
        env.pop(key, None)
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "--eval",
            recipe,
            "http-lan-test-value",
            f"PORT={port}",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout.strip() == f"http://127.0.0.1:{port}"


def test_make_keeps_explicit_api_proxy_target():
    recipe = ".PHONY: http-lan-test-value\nhttp-lan-test-value:\n\t@printf '%s\\n' '$(WEB_API_PROXY_TARGET)'\n"
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "--eval",
            recipe,
            "http-lan-test-value",
            "PORT=8000",
            "API_PROXY_TARGET=http://127.0.0.1:8800",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout.strip() == "http://127.0.0.1:8800"


def test_selected_env_overrides_the_generic_make_fallback(tmp_path):
    env_file = tmp_path / "selected.env"
    env_file.write_text(
        "API_PROXY_TARGET=http://127.0.0.1:8800\nVENOM_OPERATOR_ACCESS=trusted_lan\n"
    )
    env = {**os.environ, "API_PROXY_TARGET": "http://127.0.0.1:8000"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dotenv",
            "-f",
            str(env_file),
            "run",
            "--",
            sys.executable,
            "-c",
            "import json,os; print(json.dumps({key:os.getenv(key) for key in ('API_PROXY_TARGET','VENOM_OPERATOR_ACCESS')}))",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout) == {
        "API_PROXY_TARGET": "http://127.0.0.1:8800",
        "VENOM_OPERATOR_ACCESS": "trusted_lan",
    }
