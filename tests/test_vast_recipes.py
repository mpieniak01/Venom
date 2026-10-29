"""Offline template preparation, runtime scripts and registry contracts."""

import hashlib
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest

from tests.test_vast_operations import service as source_service
from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.images import resolve_image
from venom_core.infrastructure.providers.vast.models import digest
from venom_core.services.vast_environments.cli import dispatch, main, parser
from venom_core.services.vast_environments.openai_probe import ready
from venom_core.services.vast_environments.operations import workload
from venom_core.services.vast_environments.recipes import prepare, verify_template
from venom_core.services.vast_environments.startup import startup

HASH = "a" * 64


@pytest.fixture
def service(tmp_path):
    return source_service.__wrapped__(tmp_path)


def template(svc):
    row = {
        "hash_id": "abc",
        "configuration_sha256": HASH,
        "image": "test",
        "use_ssh": True,
        "recommended_disk_space": 100,
    }
    svc.client.templates.return_value = [row]
    return row


def test_prepare_template_and_freshness(service, tmp_path):
    svc, plan, _ = service
    row = template(svc)
    out = tmp_path / "profile.json"
    result = prepare(svc.client, plan.profile, "inspect", "abc", out)
    cfg = plan.profile.model_validate_json(out.read_text())
    assert cfg.template_hash == "abc"
    assert result["paid_resources_created"] is False
    assert out.stat().st_mode & 0o777 == 0o600
    verify_template(svc.client, cfg)
    with pytest.raises(FileExistsError):
        prepare(svc.client, plan.profile, "inspect", "abc", out)
    changed = cfg.model_copy(update={"template_configuration_sha256": "b" * 64})
    with pytest.raises(VastError, match="template_changed"):
        verify_template(svc.client, changed)
    for change, error in [
        ({"use_ssh": False}, "image_or_ssh"),
        ({"image": "other"}, "image_or_ssh"),
        ({"recommended_disk_space": None}, "disk_unknown"),
        ({"recommended_disk_space": 200}, "disk_insufficient"),
    ]:
        svc.client.templates.return_value = [{**row, **change}]
        with pytest.raises(VastError, match=error):
            verify_template(svc.client, cfg)
    svc.client.templates.return_value = []
    with pytest.raises(VastError, match="template_missing"):
        verify_template(svc.client, cfg)


@pytest.mark.parametrize("mode", ["inspect", "ollama", "vllm", "pytorch"])
def test_recipe_scripts_and_validation(service, mode, tmp_path):
    svc, plan, _ = service
    cfg = plan.profile.model_copy(
        update={
            "mode": mode,
            "model": "org/model",
            "model_digest": "b" * 40,
            "download_gb": Decimal(20),
            "worker_tasks": ["vision", "audio"],
        }
    )
    result = prepare(svc.client, cfg, mode, None, tmp_path / (mode + ".json"))
    script = result["startup"]
    assert subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0
    assert startup(cfg) == script
    assert "docker run" not in script
    assert "pip install" not in script
    if mode == "vllm":
        assert "--host 127.0.0.1" in script
        assert "--revision " in script
        assert "--gpu-memory-utilization 0.85" in script
        assert "HF_HUB_OFFLINE" not in script
        assert "HF_HUB_OFFLINE=1" in startup(
            cfg.model_copy(update={"download_gb": Decimal(0)})
        )
    if mode == "pytorch":
        assert "faster_whisper" in script
        assert "ultralytics" in script
        assert "worker_ready" in script
        assert "faster_whisper" not in startup(
            cfg.model_copy(update={"worker_tasks": []})
        )


def test_bad_recipe_and_plan_template_change(service, tmp_path):
    svc, plan, _ = service
    profile = plan.profile.model_copy(update={"download_gb": Decimal(1)})
    output = tmp_path / "bad.json"
    with pytest.raises(VastError, match="model_digest_required"):
        prepare(svc.client, profile, "ollama", None, output)
    cfg = plan.profile.model_copy(
        update={"mode": "vllm", "model": "org/x", "model_digest": "latest"}
    )
    with pytest.raises(VastError, match="huggingface_revision_required"):
        prepare(svc.client, cfg, "vllm", None, tmp_path / "bad.json")
    unverified_template_profile = plan.profile.model_copy(
        update={"template_hash": "abc"}
    )
    with pytest.raises(VastError, match="template_provenance_required"):
        verify_template(svc.client, unverified_template_profile)
    template(svc)
    cfg = plan.profile.model_copy(
        update={"template_hash": "abc", "template_configuration_sha256": HASH}
    )
    new = svc.plan(
        cfg,
        12,
        plan.max_hourly_usd,
        plan.max_total_usd,
        Path(plan.ssh_identity_file),
        tmp_path / "known",
    )
    svc.client.templates.return_value[0]["configuration_sha256"] = "b" * 64
    with pytest.raises(VastError, match="template_changed"):
        svc.create(new.plan_id)
    svc.client.create.assert_not_called()


def registry(arch="arm64", wrong=False, multi=False):
    config = json.dumps({"architecture": arch, "os": "linux"}).encode()
    config_sha = "sha256:" + hashlib.sha256(config).hexdigest()
    manifest = json.dumps({"config": {"digest": config_sha}}).encode()
    sha = "sha256:" + hashlib.sha256(manifest).hexdigest()

    def respond(req):
        if req.url.host == "auth.docker.io":
            assert "Authorization" not in req.headers
            return httpx.Response(200, json={"token": "fixture-registry-token"})
        assert req.headers["Authorization"] == "Bearer fixture-registry-token"
        if "/blobs/" in req.url.path:
            return httpx.Response(200, content=config)
        if multi and req.url.path.endswith("/latest"):
            return httpx.Response(
                200,
                json={
                    "manifests": [
                        {
                            "digest": sha,
                            "platform": {"os": "linux", "architecture": arch},
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            content=manifest,
            headers={"Docker-Content-Digest": "sha256:" + "c" * 64 if wrong else sha},
        )

    return httpx.Client(
        transport=httpx.MockTransport(respond), follow_redirects=False
    ), sha


@pytest.mark.parametrize("multi", [False, True])
def test_registry_resolution(multi):
    client, sha = registry(multi=multi)
    with client:
        result = resolve_image("ollama/ollama:latest", "arm64", client)
    assert result["image"] == "ollama/ollama@" + sha
    assert "token" not in json.dumps(result)


@pytest.mark.parametrize(
    "image",
    [
        "evil.example/repo/image:tag",
        "repo:latest",
        "org/../bad:tag",
        "org/a;id:tag",
        "org/a",
    ],
)
def test_registry_invalid_names(image):
    client, _ = registry()
    with client, pytest.raises(VastError, match="invalid_public_image"):
        resolve_image(image, "arm64", client)


def test_registry_bad_digest_and_architecture():
    client, _ = registry(wrong=True)
    with client, pytest.raises(VastError, match="digest_mismatch"):
        resolve_image("org/model:tag", "arm64", client)
    client, _ = registry(arch="amd64")
    with client, pytest.raises(VastError, match="architecture_unavailable"):
        resolve_image("org/model:tag", "arm64", client)


def test_vllm_readiness(service):
    _, plan, _ = service
    cfg = plan.profile.model_copy(
        update={"mode": "vllm", "model": "org/model", "model_digest": "b" * 40}
    )

    def respond(req):
        return httpx.Response(
            200,
            json={"data": [{"id": cfg.model}]}
            if req.method == "GET"
            else {"choices": [{"message": {"content": "OK"}}]},
        )

    with httpx.Client(
        base_url="http://127.0.0.1", transport=httpx.MockTransport(respond)
    ) as client:
        assert ready(client, cfg)["runtime"] == "ready"
        missing_model_profile = cfg.model_copy(update={"model": "absent"})
        with pytest.raises(VastError, match="model_missing"):
            ready(client, missing_model_profile)
    with httpx.Client(
        base_url="http://127.0.0.1",
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200, json={"data": [{"id": cfg.model}], "choices": []}
            )
        ),
    ) as client:
        with pytest.raises(VastError, match="model_not_ready"):
            ready(client, cfg)


def test_vllm_workload_and_cli(service, tmp_path, capsys):
    svc, plan, _ = service
    plan.profile = plan.profile.model_copy(
        update={"mode": "vllm", "model": "org/model", "model_digest": "b" * 40}
    )
    plan.startup_sha256 = digest(startup(plan.profile))
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    svc.create(plan.plan_id)
    with (
        patch(
            "venom_core.services.vast_environments.operations.inspect",
            return_value={"reasons": [], "unknown": []},
        ),
        patch("venom_core.services.vast_environments.operations.tunnel") as tunnel,
        patch(
            "venom_core.services.vast_environments.operations.probe_gpu",
            return_value={"status": "passed", "engine_kernel": "passed"},
        ),
        patch(
            "venom_core.services.vast_environments.operations.openai_ready",
            return_value={"runtime": "ready"},
        ),
    ):
        tunnel.return_value.__enter__.return_value = "http://127.0.0.1"
        assert workload(svc, plan.plan_id, "ready")["runtime"] == "ready"
    assert (
        main(["--json", "recipes"], client_factory=Mock(side_effect=AssertionError))
        == 0
    )
    assert "pytorch" in capsys.readouterr().out
    template(svc)
    args = parser().parse_args(["templates", "--hash", "abc", "--recommended"])
    assert dispatch(args, svc)[0]["hash_id"] == "abc"
    svc.client.benchmarks.return_value = {"status": "not_available"}
    assert (
        dispatch(parser().parse_args(["host-results", "--machine", "4"]), svc)["status"]
        == "not_available"
    )


def test_worker_install_is_remote_scoped_and_pinned(service):
    from pydantic import ValidationError

    from venom_core.infrastructure.providers.vast.models import WorkloadProfile
    from venom_core.services.vast_environments.recipes import validate_recipe

    _, plan, _ = service
    cfg = plan.profile.model_copy(
        update={
            "mode": "pytorch",
            "worker_packages": ["ultralytics==8.3.0"],
            "download_gb": Decimal(1),
        }
    )
    validate_recipe(cfg)
    script = startup(cfg)
    assert "worker-venv/bin/python -m pip install" in script
    assert "--system-site-packages" in script
    assert "base-constraints.txt" in script
    assert "'torch'" in script
    assert "worker-venv/bin/python -c" in script
    assert subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0
    for packages in [
        ["torch==2.0"],
        ["ultralytics"],
        ["transformers==main"],
        ["pillow==1;id"],
        ["pillow==1", "pillow==2"],
    ]:
        invalid_worker_profile = {**cfg.model_dump(), "worker_packages": packages}
        with pytest.raises(ValidationError):
            WorkloadProfile.model_validate(invalid_worker_profile)
    for update in [{"mode": "ollama"}, {"download_gb": Decimal(0)}]:
        invalid_install_profile = cfg.model_copy(update=update)
        with pytest.raises(VastError, match="worker_install_download_budget_required"):
            validate_recipe(invalid_install_profile)


def test_prepare_cli_with_image_resolution(service, tmp_path):
    svc, _, _ = service
    out = tmp_path / "prepared.json"
    args = parser().parse_args(
        [
            "prepare",
            "--recipe",
            "inspect",
            "--image",
            "ollama/ollama:latest",
            "--arch",
            "arm64",
            "--disk-gb",
            "200",
            "--download-gb",
            "2",
            "--output",
            str(out),
        ]
    )
    with patch(
        "venom_core.services.vast_environments.cli.resolve_image",
        return_value={"image": "ollama/ollama@sha256:" + HASH},
    ):
        result = dispatch(args, svc)
    assert result["profile"]["disk_gb"] == 200
    assert result["profile"]["image"].endswith(HASH)
    assert out.exists()
    args = parser().parse_args(
        [
            "prepare",
            "--profile",
            str(out),
            "--recipe",
            "inspect",
            "--output",
            str(tmp_path / "second.json"),
        ]
    )
    assert dispatch(args, svc)["profile"]["cpu_arch"] == "arm64"


def test_registry_error_contracts():
    with httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    ) as client:
        with pytest.raises(VastError, match="registry_auth_failed"):
            resolve_image("org/model:tag", "arm64", client)
    with httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(403))
    ) as client:
        with pytest.raises(VastError, match="registry_failed"):
            resolve_image("org/model:tag", "arm64", client)


def test_template_fingerprint_ignores_popularity():
    from venom_core.infrastructure.providers.vast.templates import template_snapshot

    base = {
        "hash_id": "abc",
        "name": "name",
        "image": "org/image",
        "tag": "v1",
        "env": "-e FLAG=1",
        "count_created": 10,
    }
    first = template_snapshot(base)
    assert (
        first["configuration_sha256"]
        == template_snapshot({**base, "count_created": 11, "name": "new name"})[
            "configuration_sha256"
        ]
    )
    assert (
        first["configuration_sha256"]
        != template_snapshot({**base, "env": "-e FLAG=2"})["configuration_sha256"]
    )


@pytest.mark.parametrize(
    "image,expected",
    [
        ("docker.io/org/image:tag", "org/image"),
        ("org/image@sha256:" + HASH, "org/image"),
        ("registry.example:5000/team/image:tag", "registry.example:5000/team/image"),
        ("registry.example:5000/team/image", "registry.example:5000/team/image"),
    ],
)
def test_template_repository_preserves_registry_port(image, expected):
    from venom_core.services.vast_environments.recipes import repository

    assert repository(image) == expected


def test_prepared_profile_is_private_before_first_write(service, tmp_path, monkeypatch):
    import os
    import stat

    from venom_core.services.vast_environments import recipes

    svc, plan, _ = service
    original = os.fdopen
    observed = []

    def check_mode(descriptor, mode):
        observed.append(stat.S_IMODE(os.fstat(descriptor).st_mode))
        return original(descriptor, mode)

    monkeypatch.setattr(recipes.os, "fdopen", check_mode)
    out = tmp_path / "private" / "profile.json"
    prepare(svc.client, plan.profile, "inspect", None, out)
    assert observed == [0o600]
    assert stat.S_IMODE(out.parent.stat().st_mode) == 0o700


@pytest.mark.parametrize("package", ["pillow==١.٠", "pillow==１.０"])
def test_worker_version_digits_stay_ascii(service, package):
    from pydantic import ValidationError

    from venom_core.infrastructure.providers.vast.models import WorkloadProfile

    _, plan, _ = service
    data = {**plan.profile.model_dump(), "worker_packages": [package]}
    with pytest.raises(ValidationError):
        WorkloadProfile.model_validate(data)


def test_registry_tag_stays_ascii():
    client, _ = registry()
    with client, pytest.raises(VastError, match="invalid_public_image"):
        resolve_image("org/image:é", "arm64", client)


def test_vllm_wait_includes_download_and_matches_ssh_timeout(service):
    from venom_core.services.vast_environments.operations import _provision
    from venom_core.services.vast_environments.runtime_scripts import vllm_wait_seconds

    _, plan, _ = service
    plan.profile = plan.profile.model_copy(
        update={
            "mode": "vllm",
            "download_gb": Decimal(25),
            "min_download_mbps": 500,
            "duration_minutes": 30,
        }
    )
    assert vllm_wait_seconds(plan.profile) == 700
    assert "SECONDS + 700" in startup(plan.profile)
    with (
        patch(
            "venom_core.services.vast_environments.operations.ssh_args",
            return_value=["ssh"],
        ),
        patch(
            "venom_core.services.vast_environments.operations.subprocess.run",
            return_value=Mock(returncode=0),
        ) as run,
    ):
        assert _provision(plan, {}, False)["startup"] == "completed"
    assert run.call_args.kwargs["timeout"] == 760
    capped = plan.profile.model_copy(
        update={"duration_minutes": 1, "download_gb": Decimal("1e100")}
    )
    assert vllm_wait_seconds(capped) == 60
    offline = plan.profile.model_copy(update={"download_gb": Decimal(0)})
    assert vllm_wait_seconds(offline) == 300


@pytest.mark.parametrize("existing", [True, False])
def test_vllm_reuses_loading_process(service, tmp_path, existing):
    from venom_core.services.vast_environments.runtime_scripts import vllm_script

    _, plan, _ = service
    cfg = plan.profile.model_copy(update={"mode": "vllm"})
    pid_file = tmp_path / "vllm.pid"
    # The surrounding test process stands in for an existing server that is still loading.
    pid_file.write_text(str(os.getpid()) if existing else "invalid-pid")
    script = vllm_script(cfg).replace("/workspace/venom-vast", str(tmp_path))
    stubs = f"""set -euo pipefail
exec 9>/dev/null
python3() {{ :; }}
sleep() {{ :; }}
curl() {{
  n=$(cat "{tmp_path}/polls" 2>/dev/null || echo 0)
  n=$((n + 1))
  echo "$n" > "{tmp_path}/polls"
  test "$n" -ge 4
}}
nohup() {{ echo launched >> "{tmp_path}/launches"; }}
"""
    result = subprocess.run(
        ["bash", "-s"], input=stubs + script, text=True, capture_output=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "startup.state").read_text().strip() == "ready"
    launches = tmp_path / "launches"
    if existing:
        assert not launches.exists()
    else:
        assert launches.read_text().splitlines() == ["launched"]


def test_engine_only_ollama_can_be_prepared_and_planned(service, tmp_path):
    svc, plan, _ = service
    output = tmp_path / "engine-only.json"
    result = prepare(svc.client, plan.profile, "ollama", None, output)
    profile = plan.profile.model_validate_json(output.read_text())
    assert result["recipe"]["port"] == 11434
    assert profile.model == profile.model_digest == ""
    assert profile.download_gb == 0
    assert "ollama serve" in result["startup"]
    assert "ollama pull" not in result["startup"]
    engine_plan = svc.plan(
        profile,
        12,
        plan.max_hourly_usd,
        plan.max_total_usd,
        Path(plan.ssh_identity_file),
        tmp_path / "known",
    )
    assert engine_plan.profile.mode == "ollama"
    svc.client.create.assert_not_called()


@pytest.mark.parametrize(
    "update",
    [
        {"model": "test"},
        {"model_digest": "digest"},
        {"download_gb": Decimal(1)},
        {"mode": "vllm"},
    ],
)
def test_engine_only_exception_does_not_relax_model_contract(service, tmp_path, update):
    svc, plan, _ = service
    profile = plan.profile.model_copy(update={"mode": "ollama", **update})
    with pytest.raises(VastError, match="vast.model_digest_required"):
        verify_template(svc.client, profile)
    with pytest.raises(VastError, match="vast.model_digest_required"):
        svc.plan(
            profile,
            12,
            plan.max_hourly_usd,
            plan.max_total_usd,
            Path(plan.ssh_identity_file),
            tmp_path / "known",
        )
