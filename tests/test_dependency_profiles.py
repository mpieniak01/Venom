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


@pytest.mark.parametrize("current_profile", [True, False])
def test_other_application_lock_freezes_overlap_by_effective_policy(
    tmp_path, policy, pip_report, monkeypatch, current_profile
):
    policy["groups"]["light"] = ["example==1.2.3"]
    policy["groups"]["ci"] = ["extra>=1"]
    policy["groups"]["full"] = ["extra>=1"]
    policy["constraint_groups"] = {}
    profiles.generate(tmp_path, policy)
    light = tmp_path / policy["profiles"]["light"]["lock"]
    light.parent.mkdir(parents=True)
    light.write_text(
        f"# Profile policy SHA256: {profiles.profile_policy_hash(policy, 'light')}\nexample==1.2.3\n"
    )
    digest = (
        profiles.profile_policy_hash(policy, "full") if current_profile else "stale"
    )
    full = tmp_path / policy["profiles"]["full"]["lock"]
    full.write_text(
        f"# Policy SHA256: unrelated-build-policy\n# Profile policy SHA256: {digest}\n"
        "example==1.2.3\nextra==1.2.3\n"
    )

    def resolve(command, **_kwargs):
        constraint = Path(command[command.index("--constraint") + 1]).read_text()
        assert ("extra==1.2.3" in constraint) == current_profile
        Path(command[command.index("--report") + 1]).write_text(
            json.dumps(pip_report("example", "extra"))
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", resolve)
    profiles.lock_profile(tmp_path, policy, "ci", "/isolated/bin/python")


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


# Bootstrap regressions execute the orchestration with a fake package runner;
# these tests never install packages or start any application.
@pytest.fixture
def bootstrap_runner(monkeypatch):
    from scripts import bootstrap_dependency_profile as bootstrap

    commands = []

    def run(command, *, capture=False):
        commands.append(command)
        if command[1:3] == ["-m", "venv"]:
            target = Path(command[3])
            (target / "bin").mkdir(parents=True)
            (target / "bin/python").write_text("fake interpreter")
            (target / "pyvenv.cfg").write_text("include-system-site-packages = false\n")
        stdout = "include-system-site-packages = false\n"
        if "list" in command:
            stdout = "[]"
        return SimpleNamespace(returncode=0, stdout=stdout)

    monkeypatch.setattr(bootstrap, "run", run)
    monkeypatch.setattr(
        bootstrap.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=100 * 1024**3),
    )
    return bootstrap, commands


@pytest.mark.parametrize("profile", ["light", "full", "vllm", "onnx-gpu", "academy"])
def test_bootstrap_uses_hashes_audit_and_correct_build_boundary(
    tmp_path, bootstrap_runner, profile
):
    bootstrap, commands = bootstrap_runner
    target = tmp_path / "isolated"
    bootstrap.install_profile(profiles.ROOT, profile, target)
    installs = [command for command in commands if "install" in command]
    assert len(installs) == 2
    assert all("--require-hashes" in command for command in installs)
    assert all("--no-cache-dir" in command for command in installs)
    assert "audit-locks" in next(
        command for command in commands if "audit-locks" in command
    )
    assert ("--build-constraint" in installs[-1]) == (profile == "full")
    assert (
        json.loads((target / ".venom-dependency-profile.json").read_text())["profile"]
        == profile
    )


def test_bootstrap_will_not_overwrite_an_existing_directory_without_explicit_update(
    tmp_path, bootstrap_runner
):
    bootstrap, commands = bootstrap_runner
    with pytest.raises(ValueError, match="already exists"):
        bootstrap.install_profile(profiles.ROOT, "light", tmp_path)
    assert not commands


def test_bootstrap_rejects_non_venv_updates_before_package_changes(
    tmp_path, bootstrap_runner
):
    bootstrap, commands = bootstrap_runner
    with pytest.raises(ValueError, match="not a virtual environment"):
        bootstrap.install_profile(profiles.ROOT, "light", tmp_path, update=True)
    assert not commands


def test_bootstrap_never_installs_engine_components_into_application_venv(
    bootstrap_runner,
):
    bootstrap, commands = bootstrap_runner
    with pytest.raises(ValueError, match="cannot replace"):
        bootstrap.install_profile(
            profiles.ROOT, "vllm", profiles.ROOT / ".venv", update=True
        )
    assert not commands


def test_bootstrap_existing_legacy_application_is_rejected_before_pip_install(
    tmp_path, bootstrap_runner, monkeypatch
):
    bootstrap, _ = bootstrap_runner
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin/python").write_text("fake interpreter")
    (tmp_path / "pyvenv.cfg").write_text("include-system-site-packages = false\n")
    commands = []

    def run(command, *, capture=False):
        commands.append(command)
        return SimpleNamespace(
            stdout='[{"name":"semantic-kernel","version":"1.44.0"}]'
            if "list" in command
            else "include-system-site-packages = false\n",
            returncode=0,
        )

    monkeypatch.setattr(bootstrap, "run", run)
    with pytest.raises(ValueError, match="legacy/engine"):
        bootstrap.install_profile(profiles.ROOT, "ci", tmp_path, update=True)
    assert not any("install" in command for command in commands)


def test_bootstrap_refuses_system_site_packages(
    tmp_path, bootstrap_runner, monkeypatch
):
    bootstrap, _ = bootstrap_runner
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin/python").write_text("fake interpreter")
    (tmp_path / "pyvenv.cfg").write_text("include-system-site-packages = true\n")
    monkeypatch.setattr(
        bootstrap,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout="include-system-site-packages = true\n"
        ),
    )
    with pytest.raises(ValueError, match="System-site-packages"):
        bootstrap.install_profile(profiles.ROOT, "ci", tmp_path, update=True)


def test_bootstrap_validates_artifact_receipt_before_environment_creation(
    tmp_path, bootstrap_runner
):
    bootstrap, commands = bootstrap_runner
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    policy = profiles.load_policy()
    (root / "config/dependency-profiles.json").write_text(json.dumps(policy))
    lock = root / policy["profiles"]["light"]["lock"]
    lock.parent.mkdir(parents=True)
    lock.write_text("tampered")
    lock.with_suffix(".json").write_text(
        json.dumps({"profile": "light", "lock_sha256": "incorrect"})
    )
    with pytest.raises(ValueError, match="Invalid hash-lock"):
        bootstrap.install_profile(root, "light", tmp_path / "target")
    assert not commands


def test_docker_runtime_requirement_payload_is_self_contained():
    import shlex

    dockerfile = (profiles.ROOT / "docker/backend.Dockerfile").read_text()
    payload = set()
    for line in dockerfile.splitlines():
        if line.startswith("COPY "):
            payload.update(shlex.split(line)[1:-1])
    for source in payload:
        assert (profiles.ROOT / source).exists(), source
        if source.endswith(".txt"):
            for line in (profiles.ROOT / source).read_text().splitlines():
                if line.startswith(("-r ", "-c ")):
                    assert line.split(maxsplit=1)[1] in payload, (
                        "Docker omitted a transitive requirements include"
                    )
    assert "--require-hashes" in dockerfile


def test_dependency_installing_workflows_do_not_install_unlocked_python_packages():
    import yaml

    for name in [
        "ci.yml",
        "full-ci.yml",
        "copilot-setup-steps.yml",
        "security-delta-nightly.yml",
        "lint.yml",
    ]:
        workflow = yaml.safe_load(
            (profiles.ROOT / ".github/workflows" / name).read_text()
        )
        commands = [
            step.get("run", "")
            for job in workflow["jobs"].values()
            for step in job.get("steps", [])
        ]
        assert any(
            "bootstrap_dependency_profile.py" in command for command in commands
        ), name
        assert not any(
            "pip install" in command and "--require-hashes" not in command
            for command in commands
        ), name


@pytest.mark.parametrize(
    "failure", ["unknown", "platform", "system", "missing_python", "owner", "onnx_cpu"]
)
def test_bootstrap_rejects_invalid_targets_without_package_mutations(
    tmp_path, bootstrap_runner, monkeypatch, failure
):
    bootstrap, commands = bootstrap_runner
    profile = "unknown" if failure == "unknown" else "light"
    target = tmp_path / "target"
    update = False
    if failure == "platform":
        monkeypatch.setattr(bootstrap.platform, "machine", lambda: "unsupported")
    elif failure == "system":
        target = Path(bootstrap.sys.base_prefix)
    elif failure in {"missing_python", "owner", "onnx_cpu"}:
        target.mkdir()
        (target / "pyvenv.cfg").write_text("include-system-site-packages = false\n")
        update = True
        if failure != "missing_python":
            (target / "bin").mkdir()
            (target / "bin/python").write_text("fake")
        if failure == "owner":
            profile = "vllm"
            (target / ".venom-dependency-profile.json").write_text(
                json.dumps({"profile": "light"})
            )
        if failure == "onnx_cpu":
            profile = "onnx-gpu"

            def run(command, *, capture=False):
                commands.append(command)
                return SimpleNamespace(
                    stdout='[{"name":"onnxruntime","version":"1.24.0"}]'
                    if "list" in command
                    else "include-system-site-packages = false\n",
                    returncode=0,
                )

            monkeypatch.setattr(bootstrap, "run", run)
    with pytest.raises(ValueError):
        bootstrap.install_profile(profiles.ROOT, profile, target, update=update)
    assert not any("install" in command for command in commands)


def test_bootstrap_does_not_stamp_ownership_when_verification_fails(
    tmp_path, bootstrap_runner, monkeypatch
):
    bootstrap, _ = bootstrap_runner
    original = bootstrap.run

    def run(command, **kwargs):
        if "verify" in command:
            raise subprocess.CalledProcessError(1, command)
        return original(command, **kwargs)

    monkeypatch.setattr(bootstrap, "run", run)
    target = tmp_path / "target"
    with pytest.raises(subprocess.SubprocessError):
        bootstrap.install_profile(profiles.ROOT, "light", target)
    assert not (target / ".venom-dependency-profile.json").exists()


def test_bootstrap_lock_path_cannot_escape_repository(tmp_path):
    from scripts import bootstrap_dependency_profile as bootstrap

    policy = {"profiles": {"light": {"lock": "../outside.txt"}}}
    with pytest.raises(ValueError, match="inside repository"):
        bootstrap.checked_lock(tmp_path, policy, "light")


@pytest.mark.parametrize("flags", ["", "-O2 -g3", "-O2 -g0"])
def test_bootstrap_build_flags_reach_child_without_mutating_caller(monkeypatch, flags):
    from scripts import bootstrap_dependency_profile as bootstrap

    monkeypatch.setenv("CFLAGS", flags)
    monkeypatch.delenv("CXXFLAGS", raising=False)
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    monkeypatch.delenv("PYTHONHASHSEED", raising=False)
    result = bootstrap.run(
        [
            bootstrap.sys.executable,
            "-c",
            "import json,os; print(json.dumps({k:os.environ[k] for k in "
            "('SOURCE_DATE_EPOCH','PYTHONHASHSEED','CFLAGS','CXXFLAGS')}))",
        ],
        capture=True,
    )
    observed = json.loads(result.stdout)
    assert observed["SOURCE_DATE_EPOCH"] == "946684800"
    assert observed["PYTHONHASHSEED"] == "0"
    assert observed["CFLAGS"].endswith("-g0")
    assert observed["CFLAGS"].count("-g0") == 1
    assert observed["CFLAGS"].startswith(flags)
    assert observed["CXXFLAGS"] == "-g0"
    assert bootstrap.os.environ["CFLAGS"] == flags
    assert "CXXFLAGS" not in bootstrap.os.environ
    assert "SOURCE_DATE_EPOCH" not in bootstrap.os.environ
    monkeypatch.setenv("CFLAGS", observed["CFLAGS"])
    assert bootstrap.source_build_environment()["CFLAGS"] == observed["CFLAGS"]


def test_bootstrap_subprocess_wrapper_propagates_failure(monkeypatch):
    from scripts import bootstrap_dependency_profile as bootstrap

    def fail(command, **kwargs):
        assert kwargs["check"] is True
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(bootstrap.subprocess, "run", fail)
    with pytest.raises(subprocess.SubprocessError):
        bootstrap.run(["fake"], capture=True)


@pytest.mark.parametrize("failed", [False, True])
def test_bootstrap_cli_reports_real_failure(tmp_path, monkeypatch, capsys, failed):
    from scripts import bootstrap_dependency_profile as bootstrap

    def install(*args, **kwargs):
        if failed:
            raise ValueError("failed profile")

    monkeypatch.setattr(bootstrap, "install_profile", install)
    monkeypatch.setattr(
        bootstrap.sys,
        "argv",
        ["bootstrap", "--profile", "light", "--venv", str(tmp_path), "--update"],
    )
    assert bootstrap.main() == int(failed)
    if failed:
        assert "ERROR" in capsys.readouterr().err


def test_light_verification_rejects_leftover_full_packages(
    tmp_path, policy, monkeypatch
):
    lock = tmp_path / policy["profiles"]["light"]["lock"]
    lock.parent.mkdir(parents=True)
    lock.write_text(
        f"# Profile policy SHA256: {profiles.profile_policy_hash(policy, 'light')}\nexample==1.2.3\n"
    )

    def run(command, **kwargs):
        if "list" in command:
            return SimpleNamespace(
                stdout=json.dumps(
                    [
                        {"name": "example", "version": "1.2.3"},
                        {"name": "torch", "version": "2.11.0"},
                    ]
                ),
                returncode=0,
            )
        if "check" in command:
            return SimpleNamespace(
                stdout="No broken requirements found.", stderr="", returncode=0
            )
        return SimpleNamespace(
            stdout="include-system-site-packages = false\n", returncode=0
        )

    monkeypatch.setattr(subprocess, "run", run)
    result = profiles.verify_environment(
        tmp_path, policy, "light", "/isolated/bin/python"
    )
    assert result["status"] == "FAIL"
    assert result["unexpected_packages"] == ["torch"]


def test_bootstrap_refuses_profile_downgrade_before_pip_changes(
    tmp_path, bootstrap_runner, monkeypatch
):
    bootstrap, commands = bootstrap_runner
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin/python").write_text("fake interpreter")
    (tmp_path / "pyvenv.cfg").write_text("include-system-site-packages = false\n")

    def run(command, *, capture=False):
        commands.append(command)
        return SimpleNamespace(
            stdout='[{"name":"torch","version":"2.13.0"}]'
            if "list" in command
            else "include-system-site-packages = false\n",
            returncode=0,
        )

    monkeypatch.setattr(bootstrap, "run", run)
    with pytest.raises(ValueError, match="outside the selected profile"):
        bootstrap.install_profile(profiles.ROOT, "light", tmp_path, update=True)
    assert not any("install" in command for command in commands)


def test_bootstrap_canonicalizes_dotted_distribution_names(
    tmp_path, bootstrap_runner, monkeypatch
):
    bootstrap, commands = bootstrap_runner
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin/python").write_text("fake interpreter")
    (tmp_path / "pyvenv.cfg").write_text("include-system-site-packages = false\n")

    def run(command, *, capture=False):
        commands.append(command)
        return SimpleNamespace(
            stdout='[{"name":"boolean.py","version":"5.0"}]'
            if "list" in command
            else "include-system-site-packages = false\n",
            returncode=0,
        )

    monkeypatch.setattr(bootstrap, "run", run)
    bootstrap.install_profile(profiles.ROOT, "ci", tmp_path, update=True)
    assert any("install" in command for command in commands)


def test_academy_requires_explicit_opt_in():
    from venom_core.config import Settings

    assert Settings(_env_file=None).model_fields["ENABLE_ACADEMY"].default is False


def test_bootstrap_host_storage_blocks_before_venv_mutation(
    tmp_path, bootstrap_runner, monkeypatch
):
    bootstrap, commands = bootstrap_runner
    host = tmp_path / "host-volume"
    host.mkdir()
    target = tmp_path / "new-parent" / "target"
    probes = []

    def disk_usage(path):
        probes.append(path)
        return SimpleNamespace(free=(1 if path == host else 100) * bootstrap.GIB)

    monkeypatch.setattr(bootstrap.shutil, "disk_usage", disk_usage)
    with pytest.raises(OSError, match="Insufficient free space.*host-volume"):
        bootstrap.install_profile(profiles.ROOT, "light", target, storage_root=host)
    assert probes == [tmp_path, host]
    assert commands == []
    assert not target.parent.exists()


@pytest.mark.parametrize("fail_check, expected_installs", [(2, 0), (3, 1)])
def test_bootstrap_rechecks_storage_before_each_pip_mutation(
    tmp_path, bootstrap_runner, monkeypatch, fail_check, expected_installs
):
    bootstrap, commands = bootstrap_runner
    host = tmp_path / "host-volume"
    host.mkdir()
    target = tmp_path / "target"
    host_checks = 0

    def disk_usage(path):
        nonlocal host_checks
        if path == host:
            host_checks += 1
            if host_checks == fail_check:
                return SimpleNamespace(free=0)
        return SimpleNamespace(free=100 * bootstrap.GIB)

    monkeypatch.setattr(bootstrap.shutil, "disk_usage", disk_usage)
    with pytest.raises(OSError, match="Insufficient free space"):
        bootstrap.install_profile(profiles.ROOT, "light", target, storage_root=host)
    assert target.is_dir()
    assert host_checks == fail_check
    assert (
        len([command for command in commands if "install" in command])
        == expected_installs
    )
    assert not (target / ".venom-dependency-profile.json").exists()


@pytest.mark.parametrize("enough", [False, True])
def test_bootstrap_update_checks_storage_without_recreating_venv(
    tmp_path, bootstrap_runner, monkeypatch, enough
):
    bootstrap, commands = bootstrap_runner
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin/python").write_text("fake interpreter")
    (tmp_path / "pyvenv.cfg").write_text("include-system-site-packages = false\n")
    host = tmp_path / "host-volume"
    host.mkdir()

    def disk_usage(path):
        if path == host and not enough:
            return SimpleNamespace(free=0)
        return SimpleNamespace(free=100 * bootstrap.GIB)

    monkeypatch.setattr(bootstrap.shutil, "disk_usage", disk_usage)
    if enough:
        bootstrap.install_profile(
            profiles.ROOT, "ci", tmp_path, update=True, storage_root=host
        )
    else:
        with pytest.raises(OSError, match="Insufficient free space"):
            bootstrap.install_profile(
                profiles.ROOT, "ci", tmp_path, update=True, storage_root=host
            )
    assert not any(command[1:3] == ["-m", "venv"] for command in commands)
    installs = [command for command in commands if "install" in command]
    assert len(installs) == int(enough)
    assert all("--no-cache-dir" in command for command in installs)
    assert (tmp_path / ".venom-dependency-profile.json").exists() == enough


@pytest.mark.parametrize("threshold", [0, -1, float("inf"), float("nan")])
def test_bootstrap_rejects_invalid_storage_threshold_before_mutation(
    tmp_path, bootstrap_runner, threshold
):
    bootstrap, commands = bootstrap_runner
    target = tmp_path / "target"
    with pytest.raises(ValueError, match="finite and > 0"):
        bootstrap.install_profile(
            profiles.ROOT, "light", target, minimum_free_gib=threshold
        )
    assert not commands
    assert not target.exists()


def test_bootstrap_cannot_lower_profile_storage_floor(bootstrap_runner):
    bootstrap, _ = bootstrap_runner
    for profile, floor in bootstrap.MINIMUM_FREE_GIB.items():
        assert bootstrap.required_storage_bytes(profile, 0.01) == floor * bootstrap.GIB
        assert (
            bootstrap.required_storage_bytes(profile, floor + 1)
            == (floor + 1) * bootstrap.GIB
        )


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_bootstrap_invalid_backing_volume_is_not_silently_ignored(
    tmp_path, bootstrap_runner, kind
):
    bootstrap, commands = bootstrap_runner
    host = tmp_path / "host-volume"
    if kind == "file":
        host.write_text("not a mount directory")
    with pytest.raises((OSError, ValueError)):
        bootstrap.install_profile(
            profiles.ROOT, "light", tmp_path / "target", storage_root=host
        )
    assert not commands


@pytest.mark.parametrize("threshold", ["0", "-1", "inf", "nan", "invalid"])
def test_bootstrap_cli_rejects_invalid_storage_threshold(
    tmp_path, monkeypatch, threshold
):
    from scripts import bootstrap_dependency_profile as bootstrap

    monkeypatch.setattr(
        bootstrap.sys,
        "argv",
        [
            "bootstrap",
            "--profile",
            "light",
            "--venv",
            str(tmp_path),
            "--min-free-gib",
            threshold,
        ],
    )
    with pytest.raises(SystemExit) as error:
        bootstrap.main()
    assert error.value.code == 2


def test_bootstrap_cli_forwards_storage_options(tmp_path, monkeypatch):
    from scripts import bootstrap_dependency_profile as bootstrap

    calls = []
    monkeypatch.setattr(
        bootstrap, "install_profile", lambda *args, **kwargs: calls.append(kwargs)
    )
    monkeypatch.setattr(
        bootstrap.sys,
        "argv",
        [
            "bootstrap",
            "--profile",
            "light",
            "--venv",
            str(tmp_path),
            "--storage-root",
            str(tmp_path),
            "--min-free-gib",
            "4.5",
        ],
    )
    assert bootstrap.main() == 0
    assert calls == [
        {"update": False, "storage_root": tmp_path, "minimum_free_gib": 4.5}
    ]


@pytest.mark.parametrize("free_delta", [-1, 0])
def test_bootstrap_target_volume_floor_is_inclusive_and_enforced_without_host_option(
    tmp_path, bootstrap_runner, monkeypatch, free_delta
):
    bootstrap, commands = bootstrap_runner
    free = bootstrap.MINIMUM_FREE_GIB["light"] * bootstrap.GIB + free_delta
    monkeypatch.setattr(
        bootstrap.shutil, "disk_usage", lambda _path: SimpleNamespace(free=free)
    )
    target = tmp_path / "target"
    if free_delta < 0:
        with pytest.raises(OSError, match="Insufficient free space"):
            bootstrap.install_profile(profiles.ROOT, "light", target)
        assert not commands
        assert not target.exists()
    else:
        bootstrap.install_profile(profiles.ROOT, "light", target)
        assert (target / ".venom-dependency-profile.json").exists()


@pytest.mark.parametrize("version,expected", [("24.0", "FAIL"), ("26.2.1", "PASS")])
def test_environment_cannot_qualify_with_an_unpinned_bootstrap_pip(
    tmp_path, policy, monkeypatch, version, expected
):
    lock = tmp_path / policy["profiles"]["light"]["lock"]
    lock.parent.mkdir(parents=True)
    lock.write_text(
        f"# Profile policy SHA256: {profiles.profile_policy_hash(policy, 'light')}\nexample==1.2.3\n"
    )

    def run(command, **kwargs):
        if "list" in command:
            return SimpleNamespace(
                stdout=json.dumps(
                    [
                        {"name": "example", "version": "1.2.3"},
                        {"name": "pip", "version": version},
                    ]
                ),
                returncode=0,
            )
        if "check" in command:
            return SimpleNamespace(stdout="ok", stderr="", returncode=0)
        return SimpleNamespace(
            stdout="include-system-site-packages = false\n", returncode=0
        )

    monkeypatch.setattr(subprocess, "run", run)
    result = profiles.verify_environment(
        tmp_path, policy, "light", "/isolated/bin/python"
    )
    assert result["status"] == expected
    assert bool(result["bootstrap_delta"]) == (expected == "FAIL")


@pytest.mark.parametrize(
    "version,profile_pip,expected_calls",
    [
        ("24.0", False, 1),
        ("26.2.1", False, 0),
        ("24.0", True, 0),
    ],
)
def test_refresh_bootstrap_preserves_engine_pins_and_only_updates_old_tools(
    tmp_path, monkeypatch, version, profile_pip, expected_calls
):
    from scripts import bootstrap_dependency_profile as bootstrap

    build = tmp_path / "build.txt"
    build.write_text(
        "pip==26.2.1 \\\n    --hash=sha256:"
        + "a" * 64
        + "\nsetuptools==83.0.0 \\\n    --hash=sha256:"
        + "b" * 64
        + "\n"
    )
    engine = tmp_path / "engine.txt"
    engine.write_text("setuptools==80.10.2\n" + ("pip==24.0\n" if profile_pip else ""))
    observed = []

    def run(command, **kwargs):
        manifest = Path(command[command.index("-r") + 1])
        observed.append((command, manifest, manifest.read_text()))

    monkeypatch.setattr(bootstrap, "run", run)
    monkeypatch.setattr(
        bootstrap.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=100 * bootstrap.GIB),
    )
    bootstrap.refresh_bootstrap_tools(
        tmp_path / "bin/python",
        build,
        engine,
        {"pip": version, "setuptools": "80.10.2"},
        target=tmp_path,
        required_bytes=bootstrap.GIB,
        storage_root=None,
    )
    assert len(observed) == expected_calls
    if observed:
        command, temporary_manifest, content = observed[0]
        assert "pip==26.2.1" in content and "--hash=sha256:" + "a" * 64 in content
        assert "setuptools" not in content
        assert "--no-cache-dir" in command and "--require-hashes" in command
        assert not temporary_manifest.exists()


@pytest.mark.parametrize("bad_hash", [True, False])
def test_bootstrap_refresh_cannot_mutate_pip_with_bad_hash_or_low_space(
    tmp_path, monkeypatch, bad_hash
):
    from scripts import bootstrap_dependency_profile as bootstrap

    build = tmp_path / "build.txt"
    build.write_text(
        "pip==26.2.1 \\\n    --hash=sha256:" + ("bad" if bad_hash else "a" * 64) + "\n"
    )
    engine = tmp_path / "engine.txt"
    engine.write_text("setuptools==80.10.2\n")
    calls = []
    monkeypatch.setattr(bootstrap, "run", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(
        bootstrap.shutil, "disk_usage", lambda path: SimpleNamespace(free=0)
    )
    with pytest.raises(ValueError if bad_hash else OSError):
        bootstrap.refresh_bootstrap_tools(
            tmp_path / "bin/python",
            build,
            engine,
            {"pip": "24.0"},
            target=tmp_path,
            required_bytes=bootstrap.GIB,
            storage_root=None,
        )
    assert calls == []
