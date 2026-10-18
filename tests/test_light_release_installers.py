"""Execute release launchers against isolated command doubles, never an operator stack."""

from __future__ import annotations

import os
import pty
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ["install.sh", "venom.sh"]
DEFERRED_PROFILES = [
    "full",
    "FULL",
    "full-ci",
    "onnx-cpu",
    "onnx-extras",
    "onnx-gpu",
    "vllm",
    "academy",
]


@pytest.fixture
def installer_sandbox(tmp_path):
    project = tmp_path / "project"
    scripts = project / "scripts/docker"
    scripts.mkdir(parents=True)
    for name in SCRIPTS:
        target = scripts / name
        target.write_bytes((ROOT / "scripts/docker" / name).read_bytes())
        target.chmod(0o755)
    (project / "compose").mkdir()
    (project / "compose/compose.minimal.yml").write_text("services: {}\n")
    (project / ".env.dev").write_text("SENTINEL=unchanged\n")
    (project / ".venv").mkdir()
    (project / ".venv/sentinel").write_text("unchanged venv\n")
    commands = project / "commands.log"
    fake_bin = project / "fake-bin"
    fake_bin.mkdir()
    record = (
        "#!/bin/bash\n"
        "printf '%s|%s|%s|%s\\n' \"${0##*/}\" "
        '"${VENOM_RUNTIME_PROFILE-}" "${VENOM_RUNTIME_ADDONS-}" "$*" >> "$COMMAND_LOG"\n'
    )
    for name in ("docker", "curl", "python", "python3", "pip", "venv"):
        target = fake_bin / name
        target.write_text(
            record
            + (
                "exit 97\n"
                if name in {"python", "python3", "pip", "venv"}
                else "exit 0\n"
            )
        )
        target.chmod(0o755)
    for name in ("run-release.sh", "uninstall.sh"):
        target = scripts / name
        target.write_text(record + "exit 0\n")
        target.chmod(0o755)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {"VENOM_RUNTIME_PROFILE", "VENOM_RUNTIME_ADDONS", "VENOM_INSTALL_LANG"}
    }
    environment.update(
        {
            "PATH": str(fake_bin) + os.pathsep + os.defpath,
            "COMMAND_LOG": str(commands),
            "VENOM_ENABLE_GPU": "0",
            "VENOM_COMPONENTS_DIR": str(project / "components"),
            "OPENAI_API_KEY": "isolated-test-placeholder",
        }
    )
    bash = shutil.which("bash")
    assert bash

    def snapshot():
        return {
            str(path.relative_to(project)): path.read_bytes()
            for path in project.rglob("*")
            if path.is_file()
        }

    def run(name, *arguments, settings=None, menu_input=None):
        env = {**environment, **(settings or {})}
        command = [bash, str(scripts / name), *arguments]
        if menu_input is None:
            return subprocess.run(
                command,
                cwd=project,
                env=env,
                input="",
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        master, slave = pty.openpty()
        process = subprocess.Popen(
            command,
            cwd=project,
            env=env,
            stdin=slave,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        os.close(slave)
        try:
            os.write(master, menu_input.encode())
            stdout, stderr = process.communicate(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
            os.close(master)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

    return SimpleNamespace(
        run=run, snapshot=snapshot, commands=commands, project=project
    )


def arguments_for(name):
    if name == "venom.sh":
        return ["--quick", "--action", "reinstall"]
    return ["--quick", "--mode", "reinstall", "--skip-model-pull"]


@pytest.mark.parametrize("name", SCRIPTS)
@pytest.mark.parametrize("profile", DEFERRED_PROFILES)
@pytest.mark.parametrize("source", ["argument", "environment"])
def test_deferred_profile_fails_before_any_mutation(
    installer_sandbox, name, profile, source
):
    sandbox = installer_sandbox
    before = sandbox.snapshot()
    arguments = arguments_for(name)
    settings = {}
    if source == "argument":
        arguments += ["--profile", profile]
    else:
        settings["VENOM_RUNTIME_PROFILE"] = profile
    result = sandbox.run(name, *arguments, settings=settings)
    assert result.returncode != 0
    assert "Deferred profile" in result.stderr
    assert not sandbox.commands.exists(), result.stdout + result.stderr
    assert sandbox.snapshot() == before


@pytest.mark.parametrize("name", SCRIPTS)
@pytest.mark.parametrize(
    "addons", ["vllm", "onnx", "vllm,onnx", " vLLM , ONNX ", "academy"]
)
@pytest.mark.parametrize("source", ["argument", "environment"])
def test_deferred_addons_fail_before_any_mutation(
    installer_sandbox, name, addons, source
):
    sandbox = installer_sandbox
    before = sandbox.snapshot()
    arguments = [*arguments_for(name), "--profile", "light"]
    settings = {}
    if source == "argument":
        arguments += ["--addons", addons]
    else:
        settings["VENOM_RUNTIME_ADDONS"] = addons
    result = sandbox.run(name, *arguments, settings=settings)
    assert result.returncode != 0
    assert "addons are deferred" in result.stderr
    assert not sandbox.commands.exists(), result.stdout + result.stderr
    assert sandbox.snapshot() == before


@pytest.mark.parametrize("name", SCRIPTS)
@pytest.mark.parametrize(
    "profile,canonical",
    [
        ("light", "light"),
        ("api_ollama", "light"),
        ("api", "llm_off"),
        ("api_only", "llm_off"),
        ("llm_off", "llm_off"),
    ],
)
def test_supported_profiles_dispatch_canonical_light_api_only(
    installer_sandbox, name, profile, canonical
):
    arguments = ["--quick", "--profile", profile, "--addons", "none"]
    arguments += ["--action", "status"] if name == "venom.sh" else ["--skip-model-pull"]
    result = installer_sandbox.run(name, *arguments)
    assert result.returncode == 0, result.stdout + result.stderr
    records = installer_sandbox.commands.read_text().splitlines()
    assert any(row.split("|")[1:3] == [canonical, "none"] for row in records)
    assert not any(
        row.startswith(("python|", "python3|", "pip|", "venv|")) for row in records
    )
    assert (
        installer_sandbox.project / ".env.dev"
    ).read_text() == "SENTINEL=unchanged\n"
    assert (
        installer_sandbox.project / ".venv/sentinel"
    ).read_text() == "unchanged venv\n"


@pytest.mark.parametrize("name", SCRIPTS)
def test_explicit_none_overrides_deferred_addon_environment(installer_sandbox, name):
    arguments = ["--quick", "--profile", "light", "--addons", "none"]
    arguments += ["--action", "status"] if name == "venom.sh" else ["--skip-model-pull"]
    result = installer_sandbox.run(
        name, *arguments, settings={"VENOM_RUNTIME_ADDONS": "vllm"}
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert all(
        row.split("|")[2] == "none"
        for row in installer_sandbox.commands.read_text().splitlines()
    )


@pytest.mark.parametrize(
    "language,prompt",
    [
        ("pl", "Wybierz architekturę"),
        ("en", "Select your Venom"),
        ("de", "Waehle deine Venom"),
    ],
)
@pytest.mark.parametrize("choice,canonical", [("1", "light"), ("2", "llm_off")])
def test_each_localized_menu_finishes_with_one_supported_choice_and_no_addon_prompt(
    installer_sandbox, language, prompt, choice, canonical
):
    result = installer_sandbox.run(
        "venom.sh",
        "--lang",
        language,
        "--action",
        "status",
        menu_input=choice + "\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert prompt in result.stderr
    assert "FULL" not in result.stderr
    assert "vLLM" not in result.stderr and "ONNX" not in result.stderr
    assert installer_sandbox.commands.read_text().split("|")[1:3] == [canonical, "none"]


@pytest.mark.parametrize("language", ["pl", "en", "de"])
def test_removed_full_menu_choice_fails_without_dispatch(installer_sandbox, language):
    before = installer_sandbox.snapshot()
    result = installer_sandbox.run(
        "venom.sh", "--lang", language, "--action", "reinstall", menu_input="3\n"
    )
    assert result.returncode != 0
    assert "Invalid architecture choice" in result.stderr
    assert not installer_sandbox.commands.exists()
    assert installer_sandbox.snapshot() == before
