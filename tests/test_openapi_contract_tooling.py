"""Offline regressions for deterministic exports and fail-closed contract gates."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import check_openapi_contract as gate
from scripts import export_openapi as exporter


@pytest.fixture
def schema():
    return {
        "openapi": "3.1.0",
        "info": {"title": "Fixture", "version": "1"},
        "paths": {"/audio": {"post": {"operationId": "audio", "responses": {}}}},
        "components": {"schemas": {"Voice": {"type": "string"}}},
    }


def test_export_environment_drops_operator_settings_credentials_and_pytest(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("API_OPTIONAL_MODULES", "manifest:/operator/module.json")
    monkeypatch.setenv("ENV_FILE", "/operator/.env.dev")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-not-a-secret")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "fixture")
    monkeypatch.setenv("PYTHONPATH", "/operator/packages")
    environment = exporter.isolated_environment(tmp_path)
    assert environment["API_OPTIONAL_MODULES"] == ""
    assert environment["ENV_FILE"] == os.devnull
    assert environment["HOME"] == str(tmp_path)
    assert (
        not {"OPENAI_API_KEY", "PYTEST_CURRENT_TEST", "PYTHONPATH"} & environment.keys()
    )


@pytest.mark.parametrize(
    "args",
    [
        ["--profile", "module"],
        ["--profile", "core", "--module-manifest", "module.json"],
        ["--profile", "studio"],
        ["--profile", "module", "--module-manifest", "module.json"],
        [
            "--profile",
            "studio",
            "--output",
            str(exporter.REPO_ROOT / "openapi/openapi.json"),
        ],
    ],
)
def test_non_core_exports_cannot_silently_replace_shared_contract(args):
    with pytest.raises(SystemExit) as error:
        exporter.parse_args(args)
    assert error.value.code == 2


def test_isolated_export_uses_fresh_interpreter_and_propagates_failure(
    monkeypatch, tmp_path, schema
):
    def run(command, **kwargs):
        assert command[:2] == [sys.executable, "-I"]
        assert kwargs["check"] is True
        assert kwargs["cwd"] != exporter.REPO_ROOT
        assert "--worker" in command
        assert kwargs["env"]["API_OPTIONAL_MODULES"] == ""
        target = Path(command[command.index("--output") + 1])
        target.write_text(json.dumps(schema))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(exporter.subprocess, "run", run)
    assert exporter.export_schema() == schema

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(3, args[0], stderr="fixture import failure")

    monkeypatch.setattr(exporter.subprocess, "run", fail)
    output = tmp_path / "never.json"
    assert exporter.main(["--output", str(output)]) == 1
    assert not output.exists()


def test_schema_serialization_preserves_registration_and_array_order(tmp_path):
    output = tmp_path / "nested/schema.json"
    exporter.write_schema({"z": ["b", "a"], "a": {"z": 1, "a": 2}}, output)
    assert output.read_text().startswith('{\n  "z":')
    assert json.loads(output.read_text())["z"] == ["b", "a"]


@pytest.mark.parametrize("kind", ["operation", "component", "security", "missing"])
def test_studio_parity_rejects_contract_changes(schema, kind):
    studio = copy.deepcopy(schema)
    if kind == "operation":
        studio["paths"]["/audio"]["post"]["operationId"] = "other"
    elif kind == "component":
        studio["components"]["schemas"]["Voice"]["type"] = "integer"
    elif kind == "security":
        studio["security"] = [{"token": []}]
    else:
        studio["paths"]["/missing"] = studio["paths"].pop("/audio")
    assert gate.studio_contract_errors(schema, studio)


def test_studio_allows_full_only_routes_and_components(schema):
    full = copy.deepcopy(schema)
    full["paths"]["/full-only"] = {"get": {}}
    full["components"]["schemas"]["Extra"] = {"type": "integer"}
    assert gate.studio_contract_errors(full, schema) == []


@pytest.mark.parametrize("content", [None, "{", '{"paths": {}}'])
def test_contract_comparison_detects_missing_corrupt_and_stale_json(
    tmp_path, schema, content
):
    expected = tmp_path / "expected.json"
    actual = tmp_path / "actual.json"
    actual.write_text(json.dumps(schema))
    if content is not None:
        expected.write_text(content)
    assert not gate.files_match(expected, actual)


def test_contract_comparison_ignores_json_formatting_and_checks_types(tmp_path, schema):
    expected = tmp_path / "expected.json"
    actual = tmp_path / "actual.json"
    expected.write_text(json.dumps(schema, indent=4, sort_keys=True))
    actual.write_text(json.dumps(schema))
    assert gate.files_match(expected, actual)
    expected = tmp_path / "expected.d.ts"
    actual = tmp_path / "actual.d.ts"
    expected.write_text("export type Voice = string;\n")
    actual.write_text("export type Voice = number;\n")
    assert not gate.files_match(expected, actual)


def test_check_and_update_flow_detects_drift_without_modifying_tracked_files(
    monkeypatch, tmp_path, schema
):
    root = tmp_path / "repo"
    (root / "openapi").mkdir(parents=True)
    (root / "web-next/lib/generated").mkdir(parents=True)
    expected_schema = root / "openapi/openapi.json"
    expected_types = root / "web-next/lib/generated/api-types.d.ts"
    expected_schema.write_text("{}\n")
    expected_types.write_text("stale types\n")
    monkeypatch.setattr(gate, "REPO_ROOT", root)
    monkeypatch.setattr(gate, "export_schema", lambda profile: copy.deepcopy(schema))
    monkeypatch.setattr(
        gate, "generate_types", lambda src, dst: dst.write_text("fresh types\n")
    )
    output = tmp_path / "artifacts"
    assert gate.check_contract(output) == 1
    assert expected_schema.read_text() == "{}\n"
    assert expected_types.read_text() == "stale types\n"
    assert gate.check_contract(output, update=True) == 0
    assert gate.check_contract(output) == 0
    expected_types.write_text("type drift\n")
    assert gate.check_contract(output) == 1


def test_parity_failure_cannot_update_contract_or_run_codegen(
    monkeypatch, tmp_path, schema
):
    studio = copy.deepcopy(schema)
    studio["paths"]["/audio"]["post"]["operationId"] = "drift"
    monkeypatch.setattr(
        gate, "export_schema", lambda profile: schema if profile == "core" else studio
    )
    monkeypatch.setattr(
        gate, "generate_types", lambda *args: pytest.fail("unexpected codegen")
    )
    assert gate.check_contract(tmp_path, update=True) == 1


def test_codegen_uses_local_pinned_binary_and_propagates_failure(monkeypatch, tmp_path):
    def fail(command, **kwargs):
        assert command[0] == "node"
        assert "node_modules/openapi-typescript/bin/cli.js" in command[1]
        assert kwargs["check"] is True
        raise subprocess.CalledProcessError(4, command)

    monkeypatch.setattr(gate.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        gate.generate_types(tmp_path / "schema.json", tmp_path / "types.d.ts")


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("fixture missing node"),
        subprocess.TimeoutExpired("fixture exporter", 90),
        subprocess.CalledProcessError(1, "fixture", stderr="invalid schema"),
    ],
)
def test_cli_generation_failures_are_not_green(monkeypatch, tmp_path, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(gate, "check_contract", fail)
    assert gate.main(["--output-dir", str(tmp_path)]) == 1


@pytest.fixture
def module_manifest(tmp_path, monkeypatch):
    package = tmp_path / "contract_fixture.py"
    package.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.get('/fixture')\n"
        "def endpoint() -> str:\n"
        "    raise AssertionError('Contract export invoked an endpoint')\n"
    )
    monkeypatch.delitem(sys.modules, "contract_fixture", raising=False)
    manifest = tmp_path / "module.json"
    manifest.write_text(
        json.dumps(
            {
                "module_id": "contract_fixture",
                "backend": {
                    "router_import": "contract_fixture:router",
                    "feature_flag": "ENABLE_CONTRACT_FIXTURE",
                    "module_api_version": "1.0.0",
                    "min_core_version": "1.0.0",
                    "data_policy": {
                        "storage_mode": "core_prefixed",
                        "mutation_guard": "core_environment_policy",
                        "state_files": [],
                    },
                },
            }
        )
    )
    return manifest


def test_module_export_contains_only_explicit_module(module_manifest):
    result = exporter.export_schema("module", module_manifest)
    assert set(result["paths"]) == {"/fixture"}
    assert result["info"]["title"] == "Venom module: contract_fixture"


def test_module_export_fails_when_manifest_or_router_is_unavailable(module_manifest):
    with pytest.raises(ValueError):
        exporter.module_application(module_manifest.parent / "absent.json")
    payload = json.loads(module_manifest.read_text())
    payload["backend"]["router_import"] = "missing_contract_fixture:router"
    module_manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="could not load"):
        exporter.module_application(module_manifest)


def test_real_core_export_is_independent_of_operator_configuration(
    monkeypatch, tmp_path
):
    # Importing metadata must not enter the app lifespan (models/services).
    first = exporter.export_schema("core")
    poisoned_env = tmp_path / ".env.dev"
    poisoned_env.write_text(
        "API_OPTIONAL_MODULES=manifest:/missing/operator-module.json\n"
    )
    monkeypatch.setenv("ENV_FILE", str(poisoned_env))
    monkeypatch.setenv("API_OPTIONAL_MODULES", "manifest:/missing/operator-module.json")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "force-legacy-test-startup-if-leaked")
    monkeypatch.setenv("ENABLE_AUDIO_INTERFACE", "true")
    monkeypatch.setenv("LLM_WARMUP_ON_STARTUP", "true")
    monkeypatch.setenv("RUNTIME_ADMISSION_ENABLED", "false")
    second = exporter.export_schema("core")
    assert first == second
    assert not any(
        "/rider/" in path or "/google-home/" in path for path in first["paths"]
    )
    parameters = first["paths"]["/api/v1/models/{model_name}/runtime-capabilities"][
        "get"
    ]["parameters"]
    assert any(parameter["name"] == "runtime" for parameter in parameters)
    studio = exporter.export_schema("studio")
    assert gate.studio_contract_errors(first, studio) == []
    assert "/api/v1/chat/audio/multimodal-turn" in studio["paths"]


@pytest.mark.parametrize("destination", ["openapi", "web-next/lib/generated"])
def test_check_rejects_artifacts_overlapping_tracked_files(
    monkeypatch, tmp_path, destination
):
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        gate, "export_schema", lambda *args: pytest.fail("unexpected export")
    )
    with pytest.raises(ValueError, match="overwrite"):
        gate.check_contract(tmp_path / destination)


@pytest.mark.parametrize(
    "changed_path,expected_gate",
    [
        ("openapi/openapi.json", True),
        ("web-next/lib/generated/api-types.d.ts", True),
        ("venom_core/api/routes/example.py", True),
        ("requirements/locks/ci-linux-py314.txt", True),
        (".github/workflows/ci.yml", True),
        ("docs/example.md", False),
    ],
)
def test_pr_fast_scopes_contract_changes_and_propagates_red_gate(
    tmp_path, changed_path, expected_gate
):
    root = tmp_path / "repo"
    root.mkdir()
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(root), *args],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

    git("init")
    git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "--allow-empty",
        "-m",
        "base",
    )
    target = root / changed_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("fixture change\n")
    git("add", ".")
    git(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "-m",
        "fixture",
    )
    tools = tmp_path / "bin"
    tools.mkdir()
    make = tools / "make"
    make.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CONTRACT_CALLS"\nexit 37\n')
    make.chmod(0o755)
    calls = tmp_path / "calls"
    environment.update(
        PATH=str(tools) + os.pathsep + os.environ["PATH"],
        PR_BASE_REF="HEAD~1",
        VENV=str(tmp_path / "absent-venv"),
        WSL_DISTRO_NAME="",
        CONTRACT_CALLS=str(calls),
    )
    result = subprocess.run(
        ["bash", str(exporter.REPO_ROOT / "scripts/pr_fast_check.sh")],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if expected_gate:
        assert result.returncode == 37, result.stdout + result.stderr
        assert calls.read_text().splitlines() == ["openapi-check"]
        assert "PR fast check passed" not in result.stdout
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert not calls.exists()


@pytest.mark.parametrize("expected_value,actual_value", [(True, 1), (False, 0)])
def test_json_comparison_distinguishes_boolean_and_numeric_defaults(
    tmp_path, expected_value, actual_value
):
    expected = tmp_path / "expected.json"
    actual = tmp_path / "actual.json"
    expected.write_text(json.dumps({"default": expected_value}))
    actual.write_text(json.dumps({"default": actual_value}))
    assert not gate.files_match(expected, actual)


def test_artifact_symlink_cannot_overwrite_committed_schema(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        gate, "export_schema", lambda *args: pytest.fail("unexpected export")
    )
    committed = tmp_path / "openapi/openapi.json"
    committed.parent.mkdir()
    committed.write_text("{}")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "studio.json").symlink_to(committed)
    with pytest.raises(ValueError, match="overwrite"):
        gate.check_contract(artifacts)
    assert committed.read_text() == "{}"
