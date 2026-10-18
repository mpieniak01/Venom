"""Bounded source builds require exact policy, artifact hashes and locked tools."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import bootstrap_dependency_profile as bootstrap
from scripts.dev import dependency_profiles as profiles

TOOLS = {
    "pip": "26.2.1",
    "setuptools": "83.0.0",
    "wheel": "0.48.0",
    "packaging": "26.0",
}


def write_lock(root, name, packages, sources=()):
    path = root / f"{name}.txt"
    artifacts = {
        package: {
            "version": version,
            "sha256": hashlib.sha256(package.encode()).hexdigest(),
            "url": (
                f"https://files.pythonhosted.org/packages/{package}-{version}"
                + (".tar.gz" if package in sources else "-py3-none-any.whl")
            ),
        }
        for package, version in packages.items()
    }
    content = "--index-url https://pypi.org/simple\n" + "".join(
        f"{package}=={item['version']} \\\n    --hash=sha256:{item['sha256']}\n"
        for package, item in sorted(artifacts.items())
    )
    path.write_text(content)
    path.with_suffix(".json").write_text(
        json.dumps(
            {
                "profile": name,
                "lock_sha256": hashlib.sha256(content.encode()).hexdigest(),
                "artifacts": artifacts,
            }
        )
    )
    return path


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    packages = {"pyautogui": "0.9.54"}
    profile_lock = write_lock(tmp_path, "full", packages, sources=packages)
    build_lock = write_lock(tmp_path, "build", TOOLS)
    policy = {
        "platform": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "source_distributions": packages,
        "groups": {"build": [f"{name}=={version}" for name, version in TOOLS.items()]},
        "forbidden_application_packages": [],
        "profiles": {
            "full": {"kind": "application", "lock": profile_lock.name},
            "build": {"kind": "component", "lock": build_lock.name},
        },
    }
    (tmp_path / "config").mkdir()
    (tmp_path / "config/dependency-profiles.json").write_text(json.dumps(policy))
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        if command[1:3] == ["-m", "venv"]:
            target = Path(command[-1])
            (target / "bin").mkdir(parents=True)
            (target / "bin/python").symlink_to(sys.executable)
            (target / "pyvenv.cfg").write_text("include-system-site-packages = false")
        if "-c" in command:
            return SimpleNamespace(stdout="include-system-site-packages = false")
        if "list" in command:
            return SimpleNamespace(
                stdout=json.dumps([{"name": "pyautogui", "version": "0.9.54"}])
            )
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(bootstrap, "run", run)
    monkeypatch.setattr(bootstrap, "check_storage_space", lambda *_a, **_kw: None)
    return tmp_path, policy, profile_lock, build_lock, commands


def install(candidate, *, update=False):
    root, _policy, _lock, _build, _commands = candidate
    target = root / "target"
    if update:
        (target / "bin").mkdir(parents=True)
        (target / "bin/python").symlink_to(sys.executable)
        (target / "pyvenv.cfg").write_text("include-system-site-packages = false")
    bootstrap.install_profile(root, "full", target, update=update)


@pytest.mark.parametrize("update", [False, True])
def test_approved_sources_use_locked_toolchain_before_no_isolation_build(
    candidate, update
):
    root, _policy, profile_lock, build_lock, commands = candidate
    install(candidate, update=update)
    installations = [command for command in commands if "install" in command]
    assert len(installations) == 2
    assert installations[0][-2:] == ["-r", str(build_lock)]
    assert "--only-binary=:all:" in installations[0]
    assert "--require-hashes" in installations[0]
    final = installations[1]
    assert final[final.index("-r") + 1] == str(profile_lock)
    assert "--require-hashes" in final
    assert "--only-binary=:all:" in final
    assert "--no-binary=pyautogui" in final
    assert "--no-build-isolation" in final
    assert (root / "target/.venom-dependency-profile.json").is_file()


def test_wheel_only_profile_preserves_default_install_contract(candidate):
    root, _policy, _profile, _build, commands = candidate
    write_lock(root, "full", {"pyautogui": "0.9.54"})
    install(candidate)
    final = [command for command in commands if "install" in command][-1]
    assert "--only-binary=:all:" in final
    assert "--no-build-isolation" not in final
    assert not any(argument.startswith("--no-binary") for argument in final)


@pytest.mark.parametrize(
    "fault",
    [
        "unapproved",
        "version",
        "hash",
        "lock_hash",
        "url",
        "missing_tool",
        "source_tool",
        "conflicting_tool",
        "stale_toolchain",
    ],
)
def test_source_preflight_rejects_bad_evidence_before_venv_or_pip_mutation(
    candidate, fault
):
    root, _policy, profile_lock, build_lock, commands = candidate
    receipt_path = profile_lock.with_suffix(".json")
    receipt = json.loads(receipt_path.read_text())
    artifact = receipt["artifacts"]["pyautogui"]
    if fault == "unapproved":
        policy_path = root / "config/dependency-profiles.json"
        policy = json.loads(policy_path.read_text())
        policy["source_distributions"] = {}
        policy_path.write_text(json.dumps(policy))
    elif fault == "version":
        artifact["version"] = "0.9.53"
    elif fault == "hash":
        artifact["sha256"] = "invalid"
    elif fault == "lock_hash":
        artifact["sha256"] = "b" * 64
    elif fault == "url":
        artifact["url"] = "https://example.invalid/PyAutoGUI-0.9.54.tar.gz"
    elif fault == "missing_tool":
        write_lock(
            root,
            "build",
            {name: version for name, version in TOOLS.items() if name != "wheel"},
        )
    elif fault == "source_tool":
        write_lock(root, "build", TOOLS, sources={"setuptools"})
    elif fault == "stale_toolchain":
        write_lock(root, "build", dict(TOOLS, setuptools="82.0.0"))
    elif fault == "conflicting_tool":
        write_lock(
            root,
            "full",
            {"pyautogui": "0.9.54", "packaging": "25.0"},
            sources={"pyautogui"},
        )
        receipt = json.loads(receipt_path.read_text())
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="source|Source|toolchain|artifact"):
        install(candidate)
    assert not commands
    assert not (root / "target").exists()


def source_report(name="pyautogui", version="0.9.54"):
    return {
        "version": "1",
        "install": [
            {
                "metadata": {"name": name, "version": version},
                "download_info": {
                    "url": f"https://files.pythonhosted.org/packages/{name}-{version}.tar.gz",
                    "archive_info": {"hashes": {"sha256": "a" * 64}},
                },
            }
        ],
    }


def test_generator_rejects_unknown_source_distribution():
    with pytest.raises(ValueError, match="Unapproved source distribution"):
        profiles.report_packages(
            source_report("unknown-source"), {"pyautogui": "0.9.54"}
        )


def test_generator_rejects_changed_source_distribution_version():
    with pytest.raises(ValueError, match="Unapproved source distribution"):
        profiles.report_packages(
            source_report(version="0.9.53"), {"pyautogui": "0.9.54"}
        )


def test_generator_accepts_exact_approved_source_distribution():
    packages = profiles.report_packages(source_report(), {"pyautogui": "0.9.54"})
    assert packages["pyautogui"]["version"] == "0.9.54"
    assert packages["pyautogui"]["sha256"] == "a" * 64
