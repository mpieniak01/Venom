"""Profile qualification cannot silently use another Python patch or scan target."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from scripts import bootstrap_dependency_profile as bootstrap
from scripts.dev import dependency_profiles as profiles


def target_policy():
    return {
        "schema_version": 1,
        "platform": {"python": "3.14", "system": "Linux", "machine": "x86_64"},
        "python_target": "3.14.8",
        "source": "https://pypi.org/simple",
        "groups": {"base": ["example==1.2.3"]},
        "profiles": {
            name: {
                "kind": "application",
                "groups": ["base"],
                "input": f"requirements/{name}.in",
                "lock": f"requirements/{name}.txt",
            }
            for name in ("light", "build")
        },
        "aliases": {},
        "exclusive_distributions": [],
        "forbidden_application_packages": [],
    }


def resolver_report():
    return {
        "version": "1",
        "pip_version": "26.2.1",
        "environment": {
            "python_version": "3.14",
            "python_full_version": "3.14.8",
            "platform_system": "Linux",
            "platform_machine": "x86_64",
        },
        "install": [
            {
                "metadata": {"name": "example", "version": "1.2.3"},
                "download_info": {
                    "url": "https://files.pythonhosted.org/packages/example.whl",
                    "archive_info": {"hashes": {"sha256": "a" * 64}},
                },
            }
        ],
    }


def test_lock_labels_and_binds_exact_qualified_interpreter():
    policy = target_policy()
    text, receipt = profiles.render_lock(policy, "light", resolver_report())
    assert "Linux x86_64 / Python 3.14.8" in text
    assert receipt["resolver_environment"]["python_full_version"] == "3.14.8"
    changed = copy.deepcopy(policy)
    changed["python_target"] = "3.14.9"
    assert profiles.profile_policy_hash(
        changed, "light"
    ) != profiles.profile_policy_hash(policy, "light")
    with pytest.raises(ValueError, match="requires Python 3.14.9"):
        profiles.render_lock(changed, "light", resolver_report())


@pytest.mark.parametrize("target", ["3.15.0", "3.14", "3.14.8rc1", None, 3148])
def test_invalid_python_patch_policy_is_rejected(tmp_path, target):
    policy = target_policy()
    policy["python_target"] = target
    (tmp_path / "config").mkdir()
    (tmp_path / profiles.POLICY).write_text(json.dumps(policy))
    with pytest.raises(ValueError, match="patch must match"):
        profiles.load_policy(tmp_path)


def test_bootstrap_rejects_wrong_patch_before_any_mutation(tmp_path, monkeypatch):
    policy = target_policy()
    (tmp_path / "config").mkdir()
    (tmp_path / profiles.POLICY).write_text(json.dumps(policy))
    monkeypatch.setattr(
        bootstrap.sys, "version_info", SimpleNamespace(major=3, minor=14)
    )
    monkeypatch.setattr(bootstrap.platform, "python_version", lambda: "3.14.7")
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Linux")
    monkeypatch.setattr(bootstrap.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        bootstrap, "run", lambda *_a, **_kw: pytest.fail("must not mutate")
    )
    with pytest.raises(ValueError, match="requires Python 3.14.8"):
        bootstrap.install_profile(tmp_path, "light", tmp_path / "candidate")
    assert not (tmp_path / "candidate").exists()


@pytest.mark.parametrize(
    "minor,expected", [("3.14", ">=3.14,<3.15"), ("3.12", ">=3.12,<3.13")]
)
def test_security_probe_uses_selected_python_line(tmp_path, minor, expected):
    lock = profiles.write_security_probe(
        tmp_path, {"example": "1.2.3"}, python_minor=minor
    )
    assert expected in lock.read_text()
    assert expected in (tmp_path / "pyproject.toml").read_text()


@pytest.mark.parametrize("minor", ["3.14.8", "3", "../3.14", "3.14\\n"])
def test_security_probe_rejects_invalid_python_before_write(tmp_path, minor):
    with pytest.raises(ValueError, match="Invalid Python minor"):
        profiles.write_security_probe(
            tmp_path / "probe", {"example": "1.2.3"}, python_minor=minor
        )
    assert not (tmp_path / "probe").exists()


def test_environment_with_right_packages_but_wrong_python_is_not_qualified(
    tmp_path, monkeypatch
):
    policy = target_policy()
    lock = tmp_path / policy["profiles"]["light"]["lock"]
    lock.parent.mkdir()
    lock.write_text(
        f"# Profile policy SHA256: {profiles.profile_policy_hash(policy, 'light')}\nexample==1.2.3\n"
    )

    def run(command, **_kwargs):
        if "list" in command:
            return SimpleNamespace(
                stdout=json.dumps([{"name": "example", "version": "1.2.3"}]),
                returncode=0,
            )
        if "check" in command:
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if "json,platform" in command[-1]:
            return SimpleNamespace(
                stdout=json.dumps(
                    dict(python="3.14.7", system="Linux", machine="x86_64")
                ),
                returncode=0,
            )
        return SimpleNamespace(
            stdout="include-system-site-packages = false", returncode=0
        )

    monkeypatch.setattr(profiles.subprocess, "run", run)
    result = profiles.verify_environment(
        tmp_path, policy, "light", "/candidate/bin/python"
    )
    assert result["status"] == "FAIL"
    assert not result["interpreter_matches"]
    assert result["delta"] == {}


def test_bootstrap_new_profile_space_reservations_cannot_be_lowered():
    for name in ("full", "full-ci", "multi-runtime-cuda"):
        assert (
            bootstrap.required_storage_bytes(name, 0.1)
            == bootstrap.MINIMUM_FREE_GIB[name] * bootstrap.GIB
        )


def test_update_rejects_wrong_target_before_package_mutation(tmp_path, monkeypatch):
    policy = target_policy()
    (tmp_path / "config").mkdir()
    (tmp_path / profiles.POLICY).write_text(json.dumps(policy))
    target = tmp_path / "candidate"
    (target / "bin").mkdir(parents=True)
    (target / "bin/python").touch()
    (target / "pyvenv.cfg").write_text("include-system-site-packages = false")
    monkeypatch.setattr(
        bootstrap.sys, "version_info", SimpleNamespace(major=3, minor=14)
    )
    monkeypatch.setattr(bootstrap.platform, "python_version", lambda: "3.14.8")
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Linux")
    monkeypatch.setattr(bootstrap.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(bootstrap, "checked_lock", lambda *_a: tmp_path / "lock.txt")
    monkeypatch.setattr(
        bootstrap, "source_install_options", lambda *_a: ["--only-binary=:all:"]
    )
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        assert "install" not in command
        return SimpleNamespace(
            stdout=json.dumps(dict(python="3.12.3", system="Linux", machine="x86_64"))
        )

    monkeypatch.setattr(bootstrap, "run", run)
    with pytest.raises(ValueError, match="Target interpreter does not match"):
        bootstrap.install_profile(tmp_path, "light", target, update=True)
    assert len(commands) == 1
    assert not (target / ".venom-dependency-profile.json").exists()
