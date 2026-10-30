"""Docker profile contract uses a fake CLI; no containers or providers are invoked."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "VENOM_RUNTIME_PROFILE",
    "ACTIVE_LLM_SERVER",
    "LLM_WARMUP_ON_STARTUP",
    "COMPOSE_PROJECT_NAME",
    "VENOM_CONTAINER_PREFIX",
    "VENOM_API_HOST_PORT",
    "VENOM_WEB_HOST_PORT",
    "VENOM_OLLAMA_HOST_PORT",
    "ENVIRONMENT_ROLE",
    "DB_SCHEMA",
    "CACHE_NAMESPACE",
    "QUEUE_NAMESPACE",
    "STORAGE_PREFIX",
    "ALLOW_DATA_MUTATION",
    "VENOM_PAUSE_BACKGROUND_TASKS",
    "ENABLE_AUTO_DOCUMENTATION",
    "ENABLE_AUTO_GARDENING",
    "OLLAMA_MODEL",
    "LLM_MODEL_NAME",
    "VENOM_RELEASE_VERSION",
)


def run_recipe(tmp_path, recipe="minimal", command="start", **overrides):
    binary = tmp_path / "docker"
    capture = tmp_path / "calls.jsonl"
    binary.write_text(
        f"#!{sys.executable}\n"
        "import json,os,sys\n"
        f"keys={NAMES!r}\n"
        "with open(os.environ['FAKE_DOCKER_LOG'],'a') as target:\n"
        " target.write(json.dumps({'args':sys.argv[1:],'env':{k:os.environ.get(k) for k in keys}})+'\\n')\n"
        "if sys.argv[1:2] == ['info']: print('{\"nvidia\":{}}')\n"
    )
    binary.chmod(0o700)
    env = {key: value for key, value in os.environ.items() if key not in NAMES}
    for key in ("PROFILE", "ENVIRONMENT", "VENOM_DOCKER_RECIPE"):
        env.pop(key, None)
    env.update(
        PATH=f"{tmp_path}:{env['PATH']}",
        FAKE_DOCKER_LOG=str(capture),
        VENOM_ENABLE_GPU="false",
    )
    env.update(overrides)
    script = "run-release.sh" if recipe == "release" else "stack.sh"
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/docker" / script), command],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = (
        [json.loads(line) for line in capture.read_text().splitlines()]
        if capture.exists()
        else []
    )
    return result, calls


@pytest.mark.parametrize("recipe", ["minimal", "release"])
@pytest.mark.parametrize("role", ["dev", "preprod"])
@pytest.mark.parametrize("profile", ["full", "light"])
def test_four_combinations_preserve_provider_and_environment(
    tmp_path, recipe, role, profile
):
    result, calls = run_recipe(
        tmp_path,
        recipe,
        PROFILE=profile,
        ENVIRONMENT=role,
        ACTIVE_LLM_SERVER="openrouter",
        OLLAMA_MODEL="chosen-model",
    )
    assert result.returncode == 0, result.stderr
    call = calls[-1]
    assert call["args"][-3:] == ["--no-deps", "backend", "frontend"]
    assert "--pull" in call["args"] and "never" in call["args"]
    assert ("--build" in call["args"]) == (recipe == "minimal")
    assert not any("exec" in item["args"] or "pull" in item["args"] for item in calls)
    env = call["env"]
    assert env["VENOM_RUNTIME_PROFILE"] == profile
    assert env["ACTIVE_LLM_SERVER"] == "openrouter"
    assert env["OLLAMA_MODEL"] == "chosen-model"
    assert env["LLM_WARMUP_ON_STARTUP"] == "false"
    assert env["ENVIRONMENT_ROLE"] == role
    assert env["COMPOSE_PROJECT_NAME"] == f"venom-{recipe}" + (
        "-preprod" if role == "preprod" else ""
    )
    assert env["DB_SCHEMA"] == role
    assert env["CACHE_NAMESPACE"] == ("preprod" if role == "preprod" else "venom")
    assert env["ALLOW_DATA_MUTATION"] == "0"
    assert env["VENOM_PAUSE_BACKGROUND_TASKS"] == (
        "true" if profile == "light" else None
    )


def test_preprod_cannot_inherit_dev_identity_ports_or_write_permission(tmp_path):
    result, calls = run_recipe(
        tmp_path,
        ENVIRONMENT="preprod",
        COMPOSE_PROJECT_NAME="venom-minimal",
        VENOM_CONTAINER_PREFIX="venom",
        VENOM_API_HOST_PORT="8000",
        ALLOW_DATA_MUTATION="1",
        DB_SCHEMA="dev",
        CACHE_NAMESPACE="venom",
        QUEUE_NAMESPACE="venom",
        STORAGE_PREFIX="",
    )
    assert result.returncode == 0, result.stderr
    env = calls[-1]["env"]
    assert env["COMPOSE_PROJECT_NAME"] == "venom-minimal-preprod"
    assert env["VENOM_CONTAINER_PREFIX"] == "venom-preprod"
    assert env["VENOM_API_HOST_PORT"] == "8810"
    assert env["VENOM_WEB_HOST_PORT"] == "3310"
    assert env["VENOM_OLLAMA_HOST_PORT"] == "11435"
    assert env["ALLOW_DATA_MUTATION"] == "0"
    assert {
        env[key]
        for key in ("DB_SCHEMA", "CACHE_NAMESPACE", "QUEUE_NAMESPACE", "STORAGE_PREFIX")
    } == {"preprod"}


@pytest.mark.parametrize("profile", ["full", "light"])
def test_local_engine_no_model_calls_and_explicit_warmup_policy(tmp_path, profile):
    result, calls = run_recipe(
        tmp_path,
        PROFILE=profile,
        ACTIVE_LLM_SERVER="ollama",
        LLM_WARMUP_ON_STARTUP="true",
    )
    assert result.returncode == 0, result.stderr
    assert calls[-1]["env"]["LLM_WARMUP_ON_STARTUP"] == (
        "true" if profile == "full" else "false"
    )
    assert "--no-deps" not in calls[-1]["args"]
    assert not any("exec" in call["args"] for call in calls)


def test_llm_off_is_only_a_deprecated_light_alias(tmp_path):
    result, calls = run_recipe(
        tmp_path, VENOM_RUNTIME_PROFILE="llm_off", ACTIVE_LLM_SERVER="ollama"
    )
    assert result.returncode == 0 and "deprecated" in result.stderr
    assert calls[-1]["env"]["VENOM_RUNTIME_PROFILE"] == "light"
    assert calls[-1]["env"]["ACTIVE_LLM_SERVER"] == "none"
    assert calls[-1]["args"][-3:] == ["--no-deps", "backend", "frontend"]


@pytest.mark.parametrize(
    "overrides",
    [{"PROFILE": "beast"}, {"ENVIRONMENT": "prod"}, {"VENOM_DOCKER_RECIPE": "other"}],
)
def test_invalid_public_configuration_fails_before_docker(tmp_path, overrides):
    result, calls = run_recipe(tmp_path, **overrides)
    assert result.returncode != 0
    assert calls == []


@pytest.mark.parametrize(
    "command,expected",
    [("stop", "down"), ("status", "ps"), ("pull", "pull"), ("restart", "up")],
)
def test_control_actions_use_only_the_selected_environment(tmp_path, command, expected):
    result, calls = run_recipe(
        tmp_path, command=command, ENVIRONMENT="preprod", ACTIVE_LLM_SERVER="none"
    )
    assert result.returncode == 0, result.stderr
    assert expected in calls[-1]["args"]
    assert all(
        call["env"]["COMPOSE_PROJECT_NAME"] == "venom-minimal-preprod" for call in calls
    )
    assert not any(
        "--volumes" in call["args"] or "-v" in call["args"] for call in calls
    )


@pytest.mark.parametrize("recipe", ["minimal", "release"])
def test_compose_templates_preserve_dev_volume_keys_and_parameterize_isolation(recipe):
    doc = yaml.safe_load((ROOT / "compose" / f"compose.{recipe}.yml").read_text())
    assert doc["name"] == "${COMPOSE_PROJECT_NAME:-venom-" + recipe + "}"
    assert set(doc["volumes"]) == {
        "ollama-data",
        "venom-data",
        "venom-workspace",
        "venom-logs",
    }
    for service in ("backend", "frontend", "ollama"):
        assert doc["services"][service]["container_name"].startswith(
            "${VENOM_CONTAINER_PREFIX:-venom}-"
        )
    backend = doc["services"]["backend"]
    assert backend["ports"] == ["${VENOM_API_HOST_PORT:-8000}:8000"]
    assert backend["environment"]["DB_SCHEMA"] == "${DB_SCHEMA:-dev}"
    assert (
        backend["environment"]["LLM_WARMUP_ON_STARTUP"]
        == "${LLM_WARMUP_ON_STARTUP:-false}"
    )
    for name in (
        "ENVIRONMENT_ROLE",
        "CACHE_NAMESPACE",
        "QUEUE_NAMESPACE",
        "STORAGE_PREFIX",
        "ALLOW_DATA_MUTATION",
    ):
        assert name in backend["environment"]
    assert doc["services"]["frontend"]["environment"]["NEXT_PUBLIC_API_BASE"] == ""
