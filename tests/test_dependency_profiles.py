"""Real dependency-policy regressions without loading application/model code."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.dev import dependency_profiles as profiles

# Extra profiles below are fixture data for generic graph contracts, not release support.
_EXAMPLE_POLICY = json.loads(r"""{
  "schema_version": 1,
  "platform": {
    "python": "3.12",
    "system": "Linux",
    "machine": "x86_64"
  },
  "source": "https://pypi.org/simple",
  "groups": {
    "light": [
      "agent-framework-core==1.22.0",
      "agent-framework-openai==1.17.0",
      "agent-framework-orchestrations==1.3.2",
      "openai==2.54.0",
      "mcp==1.30.0",
      "protobuf==5.29.6",
      "pydantic==2.13.4",
      "pydantic-settings==2.16.0",
      "fastapi==0.136.3",
      "uvicorn[standard]==0.40.0",
      "python-dotenv==1.2.2",
      "loguru==0.7.3",
      "aiofiles==25.1.0",
      "httpx==0.28.1",
      "aiohttp==3.14.3",
      "colorama==0.4.6",
      "rich==13.9.4",
      "tqdm==4.67.1",
      "psutil==5.9.8",
      "gitpython==3.1.60",
      "networkx==3.6.1",
      "pillow==12.3.0",
      "watchdog==6.0.0",
      "aiortc==1.14.0",
      "av==16.1.0",
      "numpy==1.26.4",
      "packaging==26.0",
      "starlette==1.3.1",
      "cryptography>=50.0.2,<51",
      "pyjwt>=2.15.1,<3",
      "pyopenssl>=26.0.0,<27",
      "werkzeug>=3.1.9,<4",
      "apscheduler>=3.10.4,<4",
      "redis==5.3.1",
      "arq==0.28.0",
      "websockets==15.0.1",
      "python-multipart==0.0.31",
      "urllib3>=2.8.0,<3",
      "requests>=2.33.0,<3",
      "google-genai==1.64.0",
      "anthropic==0.84.0",
      "tiktoken==0.13.0",
      "google-auth>=2.55.1,<3",
      "google-auth-oauthlib>=1.1.0,<2",
      "google-auth-httplib2>=0.1.1,<1",
      "google-api-python-client>=2.100.0,<3",
      "pyasn1>=0.6.4,<1",
      "PyGithub==2.8.1",
      "certifi>=2024.7.4",
      "chardet<6"
    ],
    "ci": [
      "pytest==9.0.3",
      "pytest-asyncio==1.3.0",
      "pytest-cov>=7,<8",
      "pytest-xdist==3.8.0",
      "pytest-timeout==2.4.0",
      "pre-commit>=4.5.1,<5",
      "mypy==1.17.1",
      "filelock>=3.20.3,<4",
      "virtualenv>=21.7.13,<22",
      "types-psutil",
      "types-aiofiles",
      "types-PyYAML",
      "types-docker",
      "ruff==0.14.8",
      "huggingface_hub>=1.31.0,<2",
      "pip-audit==2.10.1",
      "flake8==7.4.1",
      "types-bleach==6.4.0.20260728"
    ],
    "full": [
      "lancedb==0.25.3",
      "pyarrow==25.0.1",
      "pypdf>=6.21.1,<7",
      "marshmallow>=4.1.2,<5",
      "markitdown",
      "python-docx>=1.1,<2",
      "openapi-core==0.23.1",
      "torch==2.13.0",
      "transformers>=5.10.4,<5.18",
      "sentence-transformers",
      "timm",
      "opencv-python-headless==4.11.0.86",
      "soundfile",
      "scipy",
      "onnxruntime==1.26.0",
      "onnxruntime-genai==0.12.2",
      "onnx>=1.22.0,<2",
      "onnx-ir>=0.1.16,<1",
      "faster-whisper==1.2.1",
      "piper-tts==1.8.0",
      "sounddevice",
      "webrtcvad-wheels==2.0.14.post1",
      "ddgs",
      "tavily-python",
      "beautifulsoup4",
      "trafilatura",
      "docker>=7.1,<8",
      "asyncssh",
      "paramiko",
      "zeroconf",
      "pyperclip",
      "pyautogui>=0.9.54",
      "pynput>=1.7.6",
      "mss>=9.0.1",
      "pandas<3",
      "radon",
      "peft>=0.18,<0.19",
      "accelerate==1.15.0",
      "huggingface_hub>=1.31.0,<2"
    ],
    "vllm": [
      "vllm==0.31.0",
      "torch==2.13.0",
      "transformers>=5.10.4,<5.18",
      "openai==2.54.0",
      "mcp==2.3.0"
    ],
    "onnx-gpu": [
      "onnxruntime-gpu[cuda,cudnn]==1.26.0",
      "onnxruntime-genai-cuda==0.12.2",
      "onnx>=1.22.0,<2",
      "onnx-ir>=0.1.16,<1",
      "numpy==1.26.4"
    ],
    "academy": [
      "accelerate==1.15.0",
      "datasets==5.1.0",
      "trl==1.16.0",
      "peft==0.21.2",
      "transformers>=5.10.4,<5.18",
      "torch==2.13.0",
      "huggingface_hub>=1.31.0,<2",
      "pypandoc>=1.14,<2",
      "pypdf>=6.21.1,<7",
      "python-docx>=1.1,<2",
      "docker>=7.1,<8",
      "wandb==0.31.0",
      "tensorboard>=2.20,<3",
      "fsspec[http]>=2026.6.0,<=2026.7.0"
    ],
    "build": [
      "pip==26.2.1",
      "setuptools==83.0.0",
      "wheel==0.48.0",
      "packaging==26.0"
    ]
  },
  "profiles": {
    "light": {
      "kind": "application",
      "groups": [
        "light"
      ],
      "input": "requirements-light.txt",
      "lock": "requirements/locks/light-linux-py312.txt"
    },
    "ci": {
      "kind": "application",
      "extends": "light",
      "groups": [
        "ci"
      ],
      "input": "requirements-ci-lite.txt",
      "lock": "requirements/locks/ci-linux-py312.txt"
    },
    "full": {
      "kind": "application",
      "extends": "light",
      "groups": [
        "full"
      ],
      "input": "requirements-full.txt",
      "lock": "requirements/locks/full-linux-py312.txt"
    },
    "full-ci": {
      "kind": "application",
      "extends": "full",
      "groups": [
        "ci"
      ],
      "input": "requirements-full-ci.txt",
      "lock": "requirements/locks/full-ci-linux-py312.txt"
    },
    "vllm": {
      "kind": "component",
      "groups": [
        "vllm"
      ],
      "input": "requirements-profile-vllm.txt",
      "lock": "requirements/locks/vllm-linux-py312.txt",
      "boundary": "Dedicated interpreter and HTTP OpenAI inference endpoint; never install into the application venv."
    },
    "onnx-gpu": {
      "kind": "component",
      "groups": [
        "onnx-gpu"
      ],
      "input": "requirements-profile-onnx.txt",
      "lock": "requirements/locks/onnx-gpu-linux-py312.txt",
      "boundary": "Dedicated GPU worker interpreter; application/voice retain only CPU ORT. Worker bridge requires runtime qualification."
    },
    "academy": {
      "kind": "component",
      "groups": [
        "academy"
      ],
      "input": "requirements-academy.txt",
      "lock": "requirements/locks/academy-linux-py312.txt",
      "boundary": "Opt-in training environment/image. Does not mutate application packages; adapter merge/export/load must be qualified."
    },
    "build": {
      "kind": "component",
      "groups": [
        "build"
      ],
      "input": "requirements-build.txt",
      "lock": "requirements/locks/build-linux-py312.txt",
      "boundary": "Pinned build frontend/backend for source distributions. Use build constraints; not an application or model environment."
    }
  },
  "aliases": {
    "requirements.txt": "light",
    "requirements-runtime-common.txt": "light",
    "requirements-docker-minimal.txt": "light",
    "requirements-profile-api.txt": "light",
    "requirements-profile-web.txt": "light",
    "requirements-profile-onnx-cpu.txt": "full",
    "requirements-extras-onnx.txt": "full"
  },
  "forbidden_application_packages": [
    "semantic-kernel",
    "pyautogen",
    "autogen-agentchat",
    "autogen-core",
    "vllm",
    "onnxruntime-gpu",
    "onnxruntime-genai-cuda"
  ],
  "exclusive_distributions": [
    [
      "onnxruntime",
      "onnxruntime-gpu"
    ],
    [
      "onnxruntime-genai",
      "onnxruntime-genai-cuda"
    ]
  ],
  "constraint_groups": {
    "constraints-hf-onnx.txt": {
      "profile": "full",
      "packages": [
        "huggingface-hub",
        "transformers"
      ]
    },
    "requirements-build-constraints.txt": {
      "profile": "build",
      "packages": [
        "pip",
        "setuptools",
        "wheel",
        "packaging"
      ]
    }
  }
}""")


@pytest.fixture
def policy():
    return copy.deepcopy(_EXAMPLE_POLICY)


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


def test_one_policy_generates_current_installation_inputs():
    policy = profiles.load_policy()
    assert profiles.generate(profiles.ROOT, policy, check=True) == []
    assert (
        "agent-framework-core==1.22.0\n"
        in profiles.generated_inputs(policy)["requirements.txt"]
    )


@pytest.mark.parametrize("profile", ["ci", "full", "full-ci"])
def test_example_application_extensions_preserve_every_light_policy(policy, profile):
    base = profiles.requirements_for(policy, "light")
    extended = profiles.requirements_for(policy, profile)
    assert {name: extended[name] for name in base} == base
    assert "semantic-kernel" not in extended
    assert "vllm" not in extended
    assert "onnxruntime-gpu" not in extended


def test_example_voice_and_gpu_worker_cannot_overlap_ort_distributions(policy):
    full = profiles.requirements_for(policy, "full")
    gpu = profiles.requirements_for(policy, "onnx-gpu")
    assert "onnxruntime" in full and "onnxruntime-gpu" not in full
    assert full["webrtcvad-wheels"] == "webrtcvad-wheels==2.0.14.post1"
    assert "webrtcvad" not in full
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


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", "b" * 64),
        ("sha256", "not-a-hash"),
        ("sha256", None),
        ("url", "http://files.pythonhosted.org/example.whl"),
        ("url", "https://unapproved.invalid/example.whl"),
        ("url", "https://user@files.pythonhosted.org/example.whl"),
        ("url", None),
    ],
)
def test_lock_audit_validates_receipt_artifact_source_and_hash(
    tmp_path, locked_policy, field, value
):
    path = tmp_path / locked_policy["profiles"]["light"]["lock"]
    receipt_path = path.with_suffix(".json")
    receipt = json.loads(receipt_path.read_text())
    receipt["artifacts"]["example"][field] = value
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        profiles.audit_locks(tmp_path, locked_policy)


@pytest.mark.parametrize(
    "key,value",
    [("python", "3.11"), ("system", "Windows"), ("machine", "aarch64")],
)
def test_lock_audit_rejects_receipt_platform_mismatch(
    tmp_path, locked_policy, key, value
):
    path = tmp_path / locked_policy["profiles"]["light"]["lock"]
    receipt_path = path.with_suffix(".json")
    receipt = json.loads(receipt_path.read_text())
    receipt["platform"][key] = value
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="platform"):
        profiles.audit_locks(tmp_path, locked_policy)


@pytest.mark.parametrize(
    "replacement",
    [
        "    --hash=sha256:" + "b" * 64,
        "",
        "    --hash=sha256:" + "a" * 64 + " --hash=sha256:" + "b" * 64,
    ],
)
def test_lock_audit_checks_each_locked_artifact_hash(
    tmp_path, locked_policy, replacement
):
    path = tmp_path / locked_policy["profiles"]["light"]["lock"]
    receipt_path = path.with_suffix(".json")
    receipt = json.loads(receipt_path.read_text())
    path.write_text(
        path.read_text().replace("    --hash=sha256:" + "a" * 64, replacement)
    )
    # Keep the outer receipt valid: the artifact itself must still be checked.
    receipt["lock_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="artifact hash"):
        profiles.audit_locks(tmp_path, locked_policy)


def test_current_active_lock_receipts_remain_valid_and_unmodified():
    policy = profiles.load_policy()
    paths = [
        path
        for spec in policy["profiles"].values()
        for path in (
            profiles.ROOT / spec["lock"],
            (profiles.ROOT / spec["lock"]).with_suffix(".json"),
        )
    ]
    before = {path: path.read_bytes() for path in paths}
    result = profiles.audit_locks(profiles.ROOT, policy)
    assert result["status"] == "PASS"
    assert result["qualification"] == "LOCK_INTEGRITY_ONLY"
    assert set(result["packages"]) == {"light", "ci", "build"}
    assert {path: path.read_bytes() for path in paths} == before


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


@pytest.mark.parametrize("profile", ["light", "ci", "build"])
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
    assert "--only-binary=:all:" in installs[-1]
    assert "--build-constraint" not in installs[-1]
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
            profiles.ROOT, "build", profiles.ROOT / ".venv", update=True
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


def test_release_exposes_only_light_ci_build_and_explicit_deferred_profiles():
    policy = profiles.load_policy()
    assert set(policy["profiles"]) == {"light", "ci", "build"}
    assert set(policy["groups"]) == {"light", "ci", "build"}
    assert set(policy["aliases"].values()) == {"light"}
    assert len(policy["aliases"]) == 5
    assert set(policy["deferred_profiles"]) == {
        "full",
        "full-ci",
        "onnx-cpu",
        "onnx-extras",
        "onnx-gpu",
        "vllm",
        "academy",
    }


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


@pytest.mark.parametrize(
    "profile,package,vulnerable",
    [
        ("light", "pyjwt", "2.13.0"),
        ("light", "pyasn1", "0.6.3"),
        ("light", "urllib3", "2.7.0"),
        ("light", "cryptography", "48.0.1"),
        ("light", "werkzeug", "3.1.6"),
    ],
)
def test_profile_inputs_reject_versions_fixed_in_qualified_locks(
    policy, profile, package, vulnerable
):
    root = Path(__file__).resolve().parents[1]
    locked = profiles.read_lock(root / policy["profiles"][profile]["lock"])
    profiles.check_direct_requirements(policy, profile, locked)
    locked[package] = vulnerable
    with pytest.raises(ValueError, match="Missing or incompatible direct requirement"):
        profiles.check_direct_requirements(policy, profile, locked)


def test_scm_manifest_retains_every_direct_requirement_without_recursive_flags(policy):
    # Snyk SCM removes -r/-c directives before resolving a Pip project.
    # A scan must still receive the whole selected profile, including Light pins.
    inputs = profiles.generated_inputs(policy)
    targets = {
        spec["input"]: name for name, spec in policy["profiles"].items()
    } | policy["aliases"]
    for filename, profile in targets.items():
        lines = [
            line
            for line in inputs[filename].splitlines()
            if line and not line.startswith("#")
        ]
        assert all(not line.startswith("-") for line in lines), filename
        expected = profiles.requirements_for(policy, profile)
        actual = {
            profiles.canonicalize_name(profiles.Requirement(line).name): line
            for line in lines
        }
        assert len(lines) == len(actual), filename
        assert actual == expected, filename


def test_security_minimum_probe_distinguishes_floors_and_unbounded_declarations(policy):
    locked = {name: "1.2.3" for name in profiles.requirements_for(policy, "full")}
    packages, unbounded = profiles.security_probe_packages(
        policy, "full", locked, "minima"
    )
    assert packages["pyjwt"] == "2.15.1"
    assert packages["transformers"] == "5.10.4"
    assert "pyjwt" not in unbounded
    assert "sentence-transformers" in unbounded
    assert packages["sentence-transformers"] == locked["sentence-transformers"]
    with pytest.raises(ValueError, match="Unknown security probe"):
        profiles.security_probe_packages(policy, "full", locked, "invalid")


def test_security_minimum_probe_rejects_excluded_boundary(policy):
    policy["groups"]["light"] = ["pyjwt>=2.15.1,!=2.15.1,<3"]
    # Use the actual group owning this requirement in the policy.
    profile = {**policy["profiles"]["light"], "groups": ["light"]}
    policy["profiles"]["light"] = profile
    with pytest.raises(ValueError, match="Cannot represent declared minimum"):
        profiles.security_probe_packages(policy, "light", {"pyjwt": "2.15.2"}, "minima")


def test_security_probe_export_is_an_explicit_non_installation_inventory(tmp_path):
    import tomllib

    packages = {"pyjwt": "2.13.0", "urllib3": "2.7.0"}
    lock = profiles.write_security_probe(tmp_path, packages)
    manifest = tomllib.loads((tmp_path / "pyproject.toml").read_text())
    parsed_lock = tomllib.loads(lock.read_text())
    assert {row["name"]: row["version"] for row in parsed_lock["package"]} == packages
    assert {
        key: value
        for key, value in manifest["tool"]["poetry"]["dependencies"].items()
        if key != "python"
    } == packages
    assert "NOT an installation/release lock" in lock.read_text()
    with pytest.raises(ValueError, match="empty component inventory"):
        profiles.write_security_probe(tmp_path, {})


@pytest.mark.parametrize(
    "returncode,vulnerabilities,count,status,complete",
    [
        (0, [], 1, "PASS", True),
        (
            1,
            [{"id": "SNYK-PYTHON-PYJWT-20245319", "severity": "high"}],
            1,
            "FINDINGS",
            True,
        ),
        (2, [], 1, "ERROR", False),
        (0, [{"id": "SNYK-PYTHON-PYJWT-20245319"}], 1, "ERROR", False),
        (1, [], 1, "ERROR", False),
        (0, [], 0, "ERROR", False),
        (0, 7, 1, "ERROR", False),
    ],
)
def test_security_probe_requires_complete_consistent_snyk_result(
    tmp_path, monkeypatch, returncode, vulnerabilities, count, status, complete
):
    def run(command, **kwargs):
        assert "--package-manager=poetry" in command
        assert "--print-deps" in command
        assert "--file=probe/poetry.lock" in command
        assert "--org=mpieniak01" in command
        assert f"--policy-path={tmp_path / '.snyk'}" in command
        assert kwargs["cwd"] == tmp_path
        (tmp_path / "probe/snyk.json").write_text(
            json.dumps(
                {
                    "packageManager": "poetry",
                    "org": "mpieniak01",
                    "dependencyCount": count,
                    "vulnerabilities": vulnerabilities,
                }
            )
        )
        return SimpleNamespace(
            returncode=returncode, stdout="   └─ pyjwt @ 2.13.0\n", stderr=""
        )

    monkeypatch.setattr(profiles.subprocess, "run", run)
    result = profiles.scan_security_probe(
        tmp_path, tmp_path / "probe", {"pyjwt": "2.13.0"}, "snyk", "mpieniak01"
    )
    assert result["status"] == status
    assert result["complete"] is complete


def test_security_probe_failed_process_cannot_reuse_old_success(tmp_path, monkeypatch):
    directory = tmp_path / "probe"
    directory.mkdir()
    output = directory / "snyk.json"
    output.write_text(
        json.dumps(
            {"vulnerabilities": [], "dependencyCount": 1, "packageManager": "poetry"}
        )
    )
    monkeypatch.setattr(
        profiles.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=2, stdout="", stderr="failed"),
    )
    result = profiles.scan_security_probe(
        tmp_path, directory, {"pyjwt": "2.13.0"}, "snyk", "mpieniak01"
    )
    assert not output.exists()
    assert result["complete"] is False
    assert result["status"] == "ERROR"


def test_security_audit_requires_real_qualified_environment(
    tmp_path, monkeypatch, policy
):
    monkeypatch.setattr(profiles, "generate", lambda *a, **kw: [])
    monkeypatch.setattr(profiles, "audit_locks", lambda *a: {})
    monkeypatch.setattr(
        profiles,
        "verify_environment",
        lambda *a: {"status": "FAIL", "delta": {"pyjwt": "drift"}},
    )

    def must_not_scan(*args):
        pytest.fail("A drifted environment must not produce a security qualification")

    monkeypatch.setattr(profiles, "scan_security_probe", must_not_scan)
    result = profiles.audit_security_inputs(
        tmp_path, policy, "light", "python", tmp_path / "out", "snyk", "mpieniak01"
    )
    assert result["status"] == "ERROR"
    assert result["probes"] == {}


def test_security_probe_never_accepts_different_snyk_organization(
    tmp_path, monkeypatch
):
    def run(*args, **kwargs):
        (tmp_path / "probe/snyk.json").write_text(
            json.dumps(
                {
                    "packageManager": "poetry",
                    "org": "different-org",
                    "dependencyCount": 1,
                    "vulnerabilities": [],
                }
            )
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(profiles.subprocess, "run", run)
    result = profiles.scan_security_probe(
        tmp_path, tmp_path / "probe", {"pyjwt": "2.15.1"}, "snyk", "mpieniak01"
    )
    assert result["status"] == "ERROR"
    assert result["organization"] == "different-org"
    with pytest.raises(ValueError, match="explicit Snyk organization"):
        profiles.scan_security_probe(
            tmp_path, tmp_path / "other", {"pyjwt": "2.15.1"}, "snyk", ""
        )


@pytest.mark.parametrize(
    "tree,expected_delta,unexpected",
    [
        (
            "   └─ pyjwt @ 2.13.0\n",
            {"pyjwt": {"expected": "2.15.1", "actual": "2.13.0"}},
            [],
        ),
        (
            "   └─ urllib3 @ 2.8.0\n",
            {"pyjwt": {"expected": "2.15.1", "actual": None}},
            ["urllib3"],
        ),
        ("", {"pyjwt": {"expected": "2.15.1", "actual": None}}, []),
    ],
)
def test_security_probe_rejects_wrong_component_even_when_count_matches(
    tmp_path, monkeypatch, tree, expected_delta, unexpected
):
    def run(command, **kwargs):
        (tmp_path / "probe/snyk.json").write_text(
            json.dumps(
                {
                    "packageManager": "poetry",
                    "org": "mpieniak01",
                    "dependencyCount": 1,
                    "vulnerabilities": [],
                }
            )
        )
        return SimpleNamespace(returncode=0, stdout=tree, stderr="")

    monkeypatch.setattr(profiles.subprocess, "run", run)
    result = profiles.scan_security_probe(
        tmp_path, tmp_path / "probe", {"pyjwt": "2.15.1"}, "snyk", "mpieniak01"
    )
    assert result["status"] == "ERROR"
    assert result["component_delta"] == expected_delta
    assert result["unexpected_components"] == unexpected


def test_installed_security_probe_includes_bootstrap_with_pip_parser(
    tmp_path, monkeypatch
):
    packages = {"pip": "26.2.1", "setuptools": "83.0.0"}

    def run(command, **kwargs):
        assert "--package-manager=pip" in command
        assert "--command=/qualified/bin/python" in command
        assert "--file=probe/requirements.txt" in command
        assert (
            (tmp_path / "probe/requirements.txt")
            .read_text()
            .endswith("pip==26.2.1\nsetuptools==83.0.0\n")
        )
        (tmp_path / "probe/snyk.json").write_text(
            json.dumps(
                {
                    "packageManager": "pip",
                    "org": "mpieniak01",
                    "dependencyCount": 2,
                    "vulnerabilities": [],
                }
            )
        )
        return SimpleNamespace(
            returncode=0,
            stdout="   ├─ pip @ 26.2.1\n   └─ setuptools @ 83.0.0\n",
            stderr="",
        )

    monkeypatch.setattr(profiles.subprocess, "run", run)
    result = profiles.scan_security_probe(
        tmp_path,
        tmp_path / "probe",
        packages,
        "snyk",
        "mpieniak01",
        python="/qualified/bin/python",
    )
    assert result["status"] == "PASS"
    assert result["observed_components"] == packages


def test_security_audit_scans_verified_environment_bootstrap_not_only_lock(
    tmp_path, policy, monkeypatch
):
    packages = {"pyjwt": "2.15.1", "pip": "26.2.1"}
    monkeypatch.setattr(profiles, "generate", lambda *a, **kw: [])
    monkeypatch.setattr(profiles, "audit_locks", lambda *a: {})
    monkeypatch.setattr(
        profiles,
        "verify_environment",
        lambda *a: {"status": "PASS", "packages": packages},
    )
    monkeypatch.setattr(profiles, "read_lock", lambda *a: {"pyjwt": "2.15.1"})
    monkeypatch.setattr(
        profiles, "requirements_for", lambda *a: {"pyjwt": "pyjwt>=2.15.1"}
    )
    for file in (
        profiles.POLICY,
        policy["profiles"]["light"]["input"],
        policy["profiles"]["light"]["lock"],
        ".snyk",
    ):
        p = tmp_path / file
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("fixture")
    calls = []

    def scan(root, directory, observed, snyk, org, **kwargs):
        calls.append((dict(observed), kwargs.get("python")))
        return {
            "status": "PASS",
            "complete": True,
            "observed_components": observed,
            "findings": {},
        }

    monkeypatch.setattr(profiles, "scan_security_probe", scan)
    result = profiles.audit_security_inputs(
        tmp_path,
        policy,
        "light",
        "/qualified/bin/python",
        tmp_path / "evidence",
        "snyk",
        "mpieniak01",
    )
    assert result["complete"] is True
    assert calls == [
        ({"pyjwt": "2.15.1"}, None),
        ({"pip": "26.2.1"}, "/qualified/bin/python"),
        ({"pyjwt": "2.15.1"}, None),
    ]


def test_installed_inventory_preserves_valid_distribution_spelling(tmp_path):
    path = profiles.write_security_probe(
        tmp_path,
        {"boolean-py": "5.0"},
        installed=True,
        distribution_names={"boolean-py": "boolean.py"},
    )
    assert "boolean.py==5.0\n" in path.read_text()
    with pytest.raises(ValueError, match="does not match inventory"):
        profiles.write_security_probe(
            tmp_path,
            {"boolean-py": "5.0"},
            installed=True,
            distribution_names={"boolean-py": "other-package"},
        )


@pytest.mark.parametrize("nested_version", ["2.13.0", "?"])
def test_security_probe_cannot_hide_nested_conflicting_versions(
    tmp_path, monkeypatch, nested_version
):
    def run(command, **kwargs):
        (tmp_path / "probe/snyk.json").write_text(
            json.dumps(
                {
                    "packageManager": "poetry",
                    "org": "mpieniak01",
                    "dependencyCount": 1,
                    "vulnerabilities": [],
                }
            )
        )
        return SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=(f"   ├─ pyjwt @ 2.15.1\n   │  └─ pyjwt @ {nested_version}\n"),
        )

    monkeypatch.setattr(profiles.subprocess, "run", run)
    result = profiles.scan_security_probe(
        tmp_path, tmp_path / "probe", {"pyjwt": "2.15.1"}, "snyk", "mpieniak01"
    )
    assert result["status"] == "ERROR"
    assert result["conflicting_components"] == {
        "pyjwt": sorted(["2.15.1", nested_version])
    }


@pytest.mark.parametrize("bad_part", ["application", "bootstrap"])
def test_installed_security_inventory_never_waives_an_incomplete_subquery(
    tmp_path, monkeypatch, bad_part
):
    def scan(root, directory, packages, snyk, org, **kwargs):
        return {
            "status": "ERROR" if directory.name == bad_part else "PASS",
            "complete": directory.name != bad_part,
            "observed_components": dict(packages),
            "findings": {},
        }

    monkeypatch.setattr(profiles, "scan_security_probe", scan)
    result = profiles.scan_installed_security_inventory(
        tmp_path,
        tmp_path / "out",
        {"pyjwt": "2.15.1", "pip": "26.2.1"},
        "snyk",
        "mpieniak01",
        "/qualified/bin/python",
        {},
    )
    assert result["status"] == "ERROR"
    assert result["complete"] is False
    assert set(result["parts"]) == {"application", "bootstrap"}


def test_bootstrap_security_query_declares_wheel_packaging_dependency(
    tmp_path, monkeypatch
):
    packages = {"wheel": "0.48.0", "packaging": "26.0", "pyjwt": "2.15.1"}
    calls = {}

    def scan(root, directory, selected, snyk, org, **kwargs):
        calls[directory.name] = dict(selected)
        if directory.name == "bootstrap":
            assert selected == {"wheel": "0.48.0", "packaging": "26.0"}
        return {"complete": True, "observed_components": dict(selected), "findings": {}}

    monkeypatch.setattr(profiles, "scan_security_probe", scan)
    result = profiles.scan_installed_security_inventory(
        tmp_path,
        tmp_path / "out",
        packages,
        "snyk",
        "mpieniak01",
        "/qualified/bin/python",
        {},
    )
    assert result["complete"] is True
    assert result["scanned_packages"] == len(packages)
    assert result["observed_components"] == packages


@pytest.mark.parametrize(
    "failure",
    ["policy", "profile", "organization", "generated", "locks", "environment"],
)
def test_security_cli_replaces_old_pass_when_preflight_fails(
    tmp_path, policy, monkeypatch, capsys, failure
):
    config = tmp_path / profiles.POLICY
    config.parent.mkdir()
    config.write_text("invalid json" if failure == "policy" else json.dumps(policy))
    directory = tmp_path / "test-results/security"
    directory.mkdir(parents=True)
    report_path = directory / "report.json"
    report_path.write_text(
        json.dumps({"status": "PASS", "complete": True, "old": True})
    )
    if failure in {"locks", "environment"}:
        monkeypatch.setattr(profiles, "generate", lambda *args, **kwargs: [])
    if failure == "environment":
        monkeypatch.setattr(profiles, "audit_locks", lambda *args: {})
        lock = tmp_path / policy["profiles"]["light"]["lock"]
        lock.parent.mkdir(parents=True)
        lock.write_text(
            "# Profile policy SHA256: "
            + profiles.profile_policy_hash(policy, "light")
            + "\nexample==1.2.3\n"
        )

    def must_not_scan(*args, **kwargs):
        pytest.fail("Failed preflight must not query the security scanner")

    monkeypatch.setattr(profiles, "scan_security_probe", must_not_scan)
    monkeypatch.setattr(
        profiles.sys,
        "argv",
        [
            "dependency_profiles.py",
            "audit-security",
            "--root",
            str(tmp_path),
            "--profile",
            "missing" if failure == "profile" else "light",
            "--python",
            str(tmp_path / "missing-python"),
            "--snyk-org",
            " " if failure == "organization" else "mpieniak01",
            "--out-dir",
            "test-results/security",
        ],
    )
    assert profiles.main() == 2
    report = json.loads(report_path.read_text())
    assert report["status"] == "ERROR"
    assert report["complete"] is False
    assert report["error"]
    assert "old" not in report
    assert "Dependency profile ERROR" in capsys.readouterr().err


@pytest.mark.parametrize(
    "profile",
    ["full", "full-ci", "onnx-cpu", "onnx-extras", "onnx-gpu", "vllm", "academy"],
)
def test_deferred_bootstrap_stops_before_any_package_or_venv_mutation(
    tmp_path, bootstrap_runner, profile
):
    bootstrap, commands = bootstrap_runner
    with pytest.raises(ValueError, match="is deferred"):
        bootstrap.install_profile(profiles.ROOT, profile, tmp_path / "target")
    assert not commands
    assert not (tmp_path / "target").exists()


@pytest.mark.parametrize("action", ["verify", "lock", "audit-security"])
def test_deferred_cli_cannot_claim_profile_qualification(
    tmp_path, monkeypatch, capsys, action
):
    arguments = ["dependency_profiles.py", action, "--profile", "full"]
    if action == "audit-security":
        arguments.extend(
            [
                "--out-dir",
                "test-results/full",
                "--root",
                str(tmp_path),
                "--snyk-org",
                "example-org",
            ]
        )
        (tmp_path / "config").mkdir()
        (tmp_path / profiles.POLICY).write_text(json.dumps(profiles.load_policy()))
    monkeypatch.setattr("sys.argv", arguments)
    assert profiles.main() == (2 if action == "audit-security" else 1)
    assert "is deferred" in capsys.readouterr().err


def test_generation_does_not_mutate_retained_deferred_manifests(tmp_path):
    policy = profiles.load_policy()
    retained = {
        spec["manifest"]: b"# retained legacy input\n"
        for spec in policy["deferred_profiles"].values()
        if "manifest" in spec
    }
    retained["constraints-hf-onnx.txt"] = b"# retained legacy constraints\n"
    for name, content in retained.items():
        (tmp_path / name).write_bytes(content)
    profiles.generate(tmp_path, policy)
    assert profiles.generate(tmp_path, policy, check=True) == []
    assert all(
        (tmp_path / name).read_bytes() == content for name, content in retained.items()
    )
    assert not (tmp_path / "requirements-full-ci.txt").exists()


@pytest.mark.parametrize("mutation", ["active", "managed", "path", "reason", "status"])
def test_deferred_metadata_cannot_hide_active_or_generated_inputs(tmp_path, mutation):
    policy = profiles.load_policy()
    spec = policy["deferred_profiles"]["full"]
    if mutation == "active":
        policy["deferred_profiles"]["light"] = spec
    elif mutation == "managed":
        spec["manifest"] = "requirements.txt"
    elif mutation == "path":
        spec["manifest"] = "../escape.txt"
    elif mutation == "reason":
        spec["reason"] = ""
    else:
        spec["status"] = "qualified"
    (tmp_path / "config").mkdir()
    (tmp_path / profiles.POLICY).write_text(json.dumps(policy))
    with pytest.raises(ValueError):
        profiles.load_policy(tmp_path)
