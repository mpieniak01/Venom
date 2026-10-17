"""Real dependency-policy regressions without loading application/model code."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.dev import dependency_profiles as profiles


@pytest.fixture
def policy():
    return profiles.load_policy()


@pytest.fixture
def pip_report():
    def make(*names):
        return {
            "version": "1",
            "pip_version": "25.3",
            "environment": {
                "python_version": "3.12",
                "platform_system": "Linux",
                "platform_machine": "x86_64",
            },
            "install": [
                {
                    "metadata": {"name": name, "version": "1.2.3"},
                    "download_info": {
                        "url": f"https://files.pythonhosted.org/packages/{name}.whl",
                        "archive_info": {"hashes": {"sha256": "a" * 64}},
                    },
                }
                for name in names
            ],
        }

    return make


def test_one_policy_generates_current_installation_inputs(policy):
    assert profiles.generate(profiles.ROOT, policy, check=True) == []
    assert profiles.generated_inputs(policy)["requirements.txt"].endswith(
        "-r requirements-light.txt\n"
    )


@pytest.mark.parametrize("profile", ["ci", "full", "full-ci"])
def test_application_extensions_preserve_every_light_policy(policy, profile):
    base = profiles.requirements_for(policy, "light")
    extended = profiles.requirements_for(policy, profile)
    assert {name: extended[name] for name in base} == base
    assert "semantic-kernel" not in extended
    assert "vllm" not in extended
    assert "onnxruntime-gpu" not in extended


def test_full_voice_and_gpu_worker_cannot_overlap_ort_distributions(policy):
    full = profiles.requirements_for(policy, "full")
    gpu = profiles.requirements_for(policy, "onnx-gpu")
    assert "onnxruntime" in full and "onnxruntime-gpu" not in full
    assert "onnxruntime-gpu" in gpu and "onnxruntime" not in gpu
    assert policy["profiles"]["onnx-gpu"]["kind"] == "component"
    assert policy["profiles"]["academy"]["kind"] == "component"


def test_minimal_maf_uses_selected_released_components_not_metapackage(policy):
    light = profiles.requirements_for(policy, "light")
    assert light["agent-framework-core"] == "agent-framework-core==1.22.0"
    assert light["agent-framework-openai"] == "agent-framework-openai==1.17.0"
    assert "agent-framework" not in light
    assert light["openai"] == "openai==2.54.0"
    assert light["mcp"] == "mcp==1.30.0"


def test_cyclic_and_unknown_inheritance_fail_explicitly(policy):
    with pytest.raises(ValueError, match="Unknown profile"):
        profiles.requirements_for(policy, "missing")
    policy["profiles"]["light"]["extends"] = "ci"
    with pytest.raises(ValueError, match="Cyclic"):
        profiles.requirements_for(policy, "light")


def test_extension_cannot_repin_shared_direct_dependency(policy):
    policy["groups"]["ci"].append("openai==3.33.0")
    with pytest.raises(ValueError, match="Conflicting policies"):
        profiles.requirements_for(policy, "ci")


@pytest.mark.parametrize(
    "packages",
    [
        {"onnxruntime", "onnxruntime-gpu"},
        {"onnxruntime-genai", "onnxruntime-genai-cuda"},
    ],
)
def test_transitive_onnx_namespace_collision_is_rejected(policy, packages):
    with pytest.raises(ValueError, match="Overlapping"):
        profiles.check_packages(policy, "onnx-gpu", packages)


@pytest.mark.parametrize(
    "name", ["semantic-kernel", "pyautogen", "vllm", "onnxruntime-gpu"]
)
def test_forbidden_transitive_packages_do_not_enter_application_lock(
    policy, pip_report, name
):
    with pytest.raises(ValueError, match="Forbidden application"):
        profiles.render_lock(policy, "light", pip_report(name))


def test_generation_check_reports_drift_without_writing(tmp_path, policy):
    assert profiles.generate(tmp_path, policy)
    target = tmp_path / "requirements-light.txt"
    target.write_text("changed by hand\n")
    assert "requirements-light.txt" in profiles.generate(tmp_path, policy, check=True)
    assert target.read_text() == "changed by hand\n"
    profiles.generate(tmp_path, policy)
    assert not profiles.generate(tmp_path, policy, check=True)


@pytest.mark.parametrize("path", ["../escape.txt", "/tmp/escape.txt"])
def test_generated_paths_must_stay_inside_repository(tmp_path, path):
    with pytest.raises(ValueError, match="inside repository"):
        profiles.safe_path(tmp_path, path)


def test_policy_hash_is_order_independent_but_detects_pin_changes(policy):
    original = profiles.policy_hash(policy)
    assert original == profiles.policy_hash(dict(reversed(list(policy.items()))))
    policy["groups"]["light"].append("example==1.2.3")
    assert original != profiles.policy_hash(policy)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_install",
        "empty_install",
        "missing_hash",
        "bad_hash",
        "untrusted_source",
        "duplicate",
    ],
)
def test_incomplete_or_untrusted_resolver_report_never_produces_lock(
    policy, pip_report, mutation
):
    report = pip_report("example")
    item = report["install"][0]
    if mutation == "missing_install":
        del report["install"]
    elif mutation == "empty_install":
        report["install"] = []
    elif mutation == "missing_hash":
        del item["download_info"]["archive_info"]["hashes"]["sha256"]
    elif mutation == "bad_hash":
        item["download_info"]["archive_info"]["hashes"]["sha256"] = "not-a-hash"
    elif mutation == "untrusted_source":
        item["download_info"]["url"] = "http://invalid.example/package.whl"
    else:
        report["install"].append(copy.deepcopy(item))
    with pytest.raises(ValueError):
        profiles.render_lock(policy, "light", report)


def test_lock_pins_hashes_and_records_resolution_not_runtime_qualification(
    tmp_path, policy, pip_report
):
    text, receipt = profiles.render_lock(policy, "light", pip_report("Example_Package"))
    lock = tmp_path / "lock.txt"
    lock.write_text(text)
    assert profiles.read_lock(lock) == {"example-package": "1.2.3"}
    assert "--hash=sha256:" + "a" * 64 in text
    assert receipt["qualification"] == "RESOLVED_ONLY"
    assert receipt["resolver"]["version"] == "25.3"
    assert receipt["policy_sha256"] == profiles.policy_hash(policy)


@pytest.mark.parametrize("content", ["# no packages\n", "example==1.0\nexample==2.0\n"])
def test_empty_and_duplicate_lock_are_errors(tmp_path, content):
    path = tmp_path / "bad.txt"
    path.write_text(content)
    with pytest.raises(ValueError):
        profiles.read_lock(path)


def test_full_base_comparison_detects_removed_and_changed_transitives():
    assert profiles.inventory_delta({"a": "1", "b": "2"}, {"a": "2", "c": "3"}) == {
        "a": {"expected": "1", "actual": "2"},
        "b": {"expected": "2", "actual": None},
    }
    assert profiles.inventory_delta({"a": "1"}, {"a": "1", "b": "2"}) == {}


@pytest.mark.parametrize(
    "pip_check,system_site,version,expected",
    [
        (0, False, "1.2.3", "PASS"),
        (1, False, "1.2.3", "FAIL"),
        (0, True, "1.2.3", "FAIL"),
        (0, False, "9.9", "FAIL"),
    ],
)
def test_installed_environment_requires_lock_pip_check_and_isolated_venv(
    tmp_path, policy, monkeypatch, pip_check, system_site, version, expected
):
    lock = tmp_path / policy["profiles"]["light"]["lock"]
    lock.parent.mkdir(parents=True)
    lock.write_text(
        f"# Profile policy SHA256: {profiles.profile_policy_hash(policy, 'light')}\nexample==1.2.3\n"
    )

    def run(command, **_kwargs):
        if "list" in command:
            return SimpleNamespace(
                stdout=json.dumps([{"name": "example", "version": version}]),
                returncode=0,
            )
        if "check" in command:
            return SimpleNamespace(
                stdout="check result", stderr="", returncode=pip_check
            )
        return SimpleNamespace(
            stdout=f"include-system-site-packages = {str(system_site).lower()}\n",
            returncode=0,
        )

    monkeypatch.setattr(subprocess, "run", run)
    assert (
        profiles.verify_environment(tmp_path, policy, "light", "/isolated/bin/python")[
            "status"
        ]
        == expected
    )


@pytest.mark.parametrize("mutation", ["schema", "source", "kind", "alias", "path"])
def test_invalid_manifest_is_rejected_before_generation(tmp_path, policy, mutation):
    if mutation == "schema":
        policy["schema_version"] = 99
    elif mutation == "source":
        policy["source"] = "https://untrusted.example/simple"
    elif mutation == "kind":
        policy["profiles"]["light"]["kind"] = "unknown"
    elif mutation == "alias":
        policy["aliases"]["requirements.txt"] = "unknown"
    else:
        policy["profiles"]["light"]["lock"] = "../../escape.txt"
    (tmp_path / "config").mkdir()
    (tmp_path / profiles.POLICY).write_text(json.dumps(policy))
    with pytest.raises(ValueError):
        profiles.load_policy(tmp_path)


def test_stale_lock_cannot_verify_an_environment(tmp_path, policy):
    path = tmp_path / policy["profiles"]["light"]["lock"]
    path.parent.mkdir(parents=True)
    path.write_text("# Policy SHA256: old\nexample==1.0\n")
    with pytest.raises(ValueError, match="stale"):
        profiles.verify_environment(tmp_path, policy, "light", "/isolated/bin/python")


def test_lock_uses_clean_resolver_report_and_frozen_parent(
    tmp_path, policy, pip_report, monkeypatch
):
    policy["groups"]["light"] = ["example==1.2.3"]
    policy["groups"]["ci"] = ["extra==1.2.3"]
    profiles.generate(tmp_path, policy)
    light = tmp_path / policy["profiles"]["light"]["lock"]
    light.parent.mkdir(parents=True)
    light.write_text(
        f"# Profile policy SHA256: {profiles.profile_policy_hash(policy, 'light')}\nexample==1.2.3\n"
    )
    commands = []

    def resolve(command, **kwargs):
        commands.append(command)
        assert "--dry-run" in command and "--ignore-installed" in command
        assert "--constraint" in command
        constraint = Path(command[command.index("--constraint") + 1])
        assert "example==1.2.3" in constraint.read_text()
        Path(command[command.index("--report") + 1]).write_text(
            json.dumps(pip_report("example", "extra"))
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", resolve)
    path = profiles.lock_profile(tmp_path, policy, "ci", "/isolated/bin/python")
    assert profiles.read_lock(path) == {"example": "1.2.3", "extra": "1.2.3"}
    receipt = json.loads(path.with_suffix(".json").read_text())
    assert receipt["qualification"] == "RESOLVED_ONLY"
    assert len(commands) == 1


@pytest.mark.parametrize(
    "failure",
    [
        "resolver",
        "missing_parent_package",
        "changed_parent_version",
        "stale_parent",
        "stale_inputs",
        "wrong_platform",
    ],
)
def test_failed_resolution_never_emits_a_qualified_or_partial_lock(
    tmp_path, policy, pip_report, monkeypatch, failure
):
    profiles.generate(tmp_path, policy)
    light = tmp_path / policy["profiles"]["light"]["lock"]
    light.parent.mkdir(parents=True)
    digest = (
        "old"
        if failure == "stale_parent"
        else profiles.profile_policy_hash(policy, "light")
    )
    light.write_text(f"# Profile policy SHA256: {digest}\nexample==1.2.3\n")
    if failure == "stale_inputs":
        (tmp_path / "requirements-ci-lite.txt").write_text("stale")
    if failure == "wrong_platform":
        monkeypatch.setattr(profiles.platform, "machine", lambda: "unsupported")

    def resolve(command, **_kwargs):
        if failure == "resolver":
            raise subprocess.CalledProcessError(1, command)
        report = pip_report(
            "unrelated" if failure == "missing_parent_package" else "example"
        )
        if failure == "changed_parent_version":
            report["install"][0]["metadata"]["version"] = "9.9"
        Path(command[command.index("--report") + 1]).write_text(json.dumps(report))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", resolve)
    with pytest.raises((ValueError, subprocess.SubprocessError)):
        profiles.lock_profile(tmp_path, policy, "ci", "/isolated/bin/python")
    assert not (tmp_path / policy["profiles"]["ci"]["lock"]).exists()


@pytest.mark.parametrize(
    "action,extra,expected",
    [
        ("generate", [], 0),
        ("generate", ["--check"], 1),
        ("generate", ["--profile", "missing"], 1),
        ("verify", [], 1),
    ],
)
def test_cli_returns_nonzero_for_stale_missing_or_invalid_inputs(
    tmp_path, policy, monkeypatch, capsys, action, extra, expected
):
    (tmp_path / "config").mkdir()
    (tmp_path / profiles.POLICY).write_text(json.dumps(policy))
    monkeypatch.setattr(
        profiles.sys,
        "argv",
        ["dependency_profiles.py", action, "--root", str(tmp_path), *extra],
    )
    assert profiles.main() == expected
    output = capsys.readouterr()
    assert output.out or output.err


@pytest.mark.parametrize(
    "key,value",
    [
        ("python_version", "3.11"),
        ("platform_system", "Windows"),
        ("platform_machine", "aarch64"),
    ],
)
def test_resolver_report_from_another_interpreter_or_platform_is_rejected(
    policy, pip_report, key, value
):
    report = pip_report("example")
    report["environment"][key] = value
    with pytest.raises(ValueError, match="interpreter"):
        profiles.render_lock(policy, "light", report)


def test_unrelated_component_changes_do_not_invalidate_light_or_ci_lock(policy):
    light = profiles.profile_policy_hash(policy, "light")
    ci = profiles.profile_policy_hash(policy, "ci")
    policy["groups"]["academy"].append("example-training-tool==1.0")
    policy["groups"]["full"].append("example-local-feature==1.0")
    assert profiles.profile_policy_hash(policy, "light") == light
    assert profiles.profile_policy_hash(policy, "ci") == ci
    policy["groups"]["light"].append("example==1.0")
    assert profiles.profile_policy_hash(policy, "light") != light


@pytest.fixture
def locked_policy(tmp_path, policy, pip_report):
    for group in policy["groups"]:
        policy["groups"][group] = ["example>=1"]
    policy["constraint_groups"] = {}
    profiles.generate(tmp_path, policy)
    for name, spec in policy["profiles"].items():
        content, receipt = profiles.render_lock(policy, name, pip_report("example"))
        path = tmp_path / spec["lock"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.with_suffix(".json").write_text(json.dumps(receipt))
    return policy


def test_complete_lock_audit_checks_all_components_and_shared_application_graph(
    tmp_path, locked_policy
):
    result = profiles.audit_locks(tmp_path, locked_policy)
    assert result["status"] == "PASS"
    assert result["qualification"] == "LOCK_INTEGRITY_ONLY"
    assert set(result["packages"]) == set(locked_policy["profiles"])


@pytest.mark.parametrize(
    "mutation",
    [
        "receipt_owner",
        "lock_hash",
        "policy_hash",
        "empty_artifacts",
        "wrong_artifact_version",
    ],
)
def test_lock_audit_rejects_tampered_or_incomplete_receipts(
    tmp_path, locked_policy, mutation
):
    path = tmp_path / locked_policy["profiles"]["light"]["lock"]
    receipt_path = path.with_suffix(".json")
    receipt = json.loads(receipt_path.read_text())
    if mutation == "receipt_owner":
        receipt["profile"] = "other"
    elif mutation == "lock_hash":
        path.write_text(path.read_text() + "# changed\n")
    elif mutation == "policy_hash":
        receipt["profile_policy_sha256"] = "old"
    elif mutation == "empty_artifacts":
        receipt["artifacts"] = {}
    else:
        receipt["artifacts"]["example"]["version"] = "9.9"
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        profiles.audit_locks(tmp_path, locked_policy)


def test_lock_audit_rejects_application_transitive_version_drift(
    tmp_path, locked_policy, pip_report
):
    report = pip_report("example")
    report["install"][0]["metadata"]["version"] = "2.0"
    text, receipt = profiles.render_lock(locked_policy, "full", report)
    path = tmp_path / locked_policy["profiles"]["full"]["lock"]
    path.write_text(text)
    path.with_suffix(".json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="Shared application versions differ"):
        profiles.audit_locks(tmp_path, locked_policy)


def test_lock_cannot_omit_requested_direct_package(policy):
    with pytest.raises(ValueError, match="direct requirement"):
        profiles.check_direct_requirements(policy, "light", {"openai": "2.54.0"})
