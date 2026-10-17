"""Offline acceptance of shared serving suite, OCI metadata and image environments."""

import ast
import contextlib
import io
import json
import subprocess
from unittest.mock import Mock, patch

import httpx
import pytest

from tests.test_vast_operations import service as source_service
from tests.test_vast_qualification import gpu, inspection
from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.image_metadata import runtime_metadata
from venom_core.infrastructure.providers.vast.images import resolve_image
from venom_core.services.vast_environments.evaluation import OllamaProbe
from venom_core.services.vast_environments.gpu_probe import CUDA_SCRIPT, REMOTE_SCRIPT
from venom_core.services.vast_environments.interpreters import (
    SELECT_SCRIPT,
    select_shell,
)
from venom_core.services.vast_environments.openai_probe import (
    OpenAIProbe,
    openai_payload,
)
from venom_core.services.vast_environments.operations import workload


@pytest.fixture
def service(tmp_path):
    return source_service.__wrapped__(tmp_path)


def openai_client(profile, missing=False, broken=False):
    def respond(request):
        if request.method == "GET":
            return httpx.Response(
                200, json={"data": [] if missing else [{"id": profile.model}]}
            )
        body = json.loads(request.content)
        if not body.get("stream"):
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "OK"}}]}
            )
        message = body["messages"][0]["content"]
        text = (
            "green yellow"
            if isinstance(message, list)
            else ('{"ok":true}' if body.get("response_format") else "steps")
        )
        delta = {"content": text}
        if body.get("tools"):
            delta = {
                "tool_calls": [
                    {"index": 0, "function": {"name": "read_benchmark_sensor"}}
                ]
            }
        rows = [
            {"choices": [{"delta": delta, "finish_reason": None}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 20, "completion_tokens": 10}},
        ]
        content = ": ping\n\n" + "".join(
            "data: " + json.dumps(row) + "\n\n" for row in rows
        )
        if broken:
            content = 'data: {"error":"private diagnostic must not escape"}\n\n'
        else:
            content += "data: [DONE]\n\n"
        return httpx.Response(200, content=content)

    return httpx.Client(
        base_url="http://127.0.0.1", transport=httpx.MockTransport(respond)
    )


@pytest.mark.parametrize(
    "capabilities,expected", [([], 9), (["json", "vision", "tools"], 12)]
)
def test_shared_openai_suite(service, capabilities, expected):
    _, plan, _ = service
    plan.profile.mode = "vllm"
    plan.profile.runtime.capabilities = capabilities
    with openai_client(plan.profile) as client:
        probe = OpenAIProbe(client, plan.profile)
        result = probe.benchmark()
        assert result["status"] == "suitable"
        assert len(result["samples"]) == expected
        assert result["samples"][0]["eval_count"] == 10
        assert result["samples"][0]["characters_s"] > 0
        assert "decode_tokens_s" not in result["samples"][0]
        assert result["samples"][0]["eval_duration"] is None
        assert result["suite_version"] == "venom-vast-model-v4"
        assert ("vision" in result["skipped_capabilities"]) == (expected == 9)
        assert all(row.get("correct", True) for row in result["samples"])


def test_openai_errors_and_incomplete_stream(service):
    _, plan, _ = service
    with (
        openai_client(plan.profile, missing=True) as client,
        pytest.raises(VastError, match="model_missing"),
    ):
        OpenAIProbe(client, plan.profile).metadata()
    with openai_client(plan.profile, broken=True) as client:
        result = OpenAIProbe(client, plan.profile).benchmark()
        assert result["status"] == "unsuitable"
        assert "private diagnostic" not in json.dumps(result)

    def incomplete(request):
        return httpx.Response(
            200,
            content='data: {"choices":[{"delta":{"content":"hello"}}]}\n\ndata: [DONE]\n',
        )

    with httpx.Client(
        base_url="http://127.0.0.1", transport=httpx.MockTransport(incomplete)
    ) as client:
        probe = OpenAIProbe(client, plan.profile)
        assert probe.sample("text", probe._payload("text"))["status"] == "incomplete"

    def huge(request):
        return httpx.Response(200, content="data: " + "a" * 2_000_001 + "\n")

    with httpx.Client(
        base_url="http://127.0.0.1", transport=httpx.MockTransport(huge)
    ) as client:
        probe = OpenAIProbe(client, plan.profile)
        assert probe.sample("text", probe._payload("text"))["status"] == "error"


def test_runtime_operation_vllm_qualifies_and_saves_without_cycles(service):
    svc, plan, _ = service
    from venom_core.infrastructure.providers.vast.models import digest
    from venom_core.services.vast_environments.startup import startup

    plan.profile.mode = "vllm"
    plan.profile.model = "org/model"
    plan.profile.model_digest = "b" * 40
    plan.profile.runtime.min_characters_s = 0.001
    plan.startup_sha256 = digest(startup(plan.profile))
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    svc.create(plan.plan_id)
    client = openai_client(plan.profile)
    with (
        client,
        patch(
            "venom_core.services.vast_environments.operations.inspect",
            return_value=inspection(),
        ),
        patch("venom_core.services.vast_environments.operations.tunnel") as tunnel,
        patch(
            "venom_core.services.vast_environments.operations.probe_gpu",
            return_value=gpu(),
        ) as hardware,
        patch(
            "venom_core.services.vast_environments.operations.httpx.Client"
        ) as factory,
    ):
        tunnel.return_value.__enter__.return_value = "http://127.0.0.1"
        # Build before replacing the shared httpx.Client name.
        factory.return_value.__enter__.return_value = client
        result = workload(svc, plan.plan_id, "benchmark")
        assert result["status"] == "suitable"
        assert result["qualification_report"]["performance_evaluated"] is True
        assert result["qualification_report"]["observed"]["engine_version"] == "0.30.0"
        assert hardware.call_count == 1
    assert svc.journal.record(plan.plan_id).reports["benchmark"]["status"] == "suitable"
    json.dumps(result)


def test_runtime_does_not_benchmark_unqualified_gpu(service):
    from venom_core.infrastructure.providers.vast.models import digest
    from venom_core.services.vast_environments.startup import startup

    svc, plan, _ = service
    plan.profile.mode = "vllm"
    plan.profile.model = "org/model"
    plan.profile.model_digest = "b" * 40
    plan.startup_sha256 = digest(startup(plan.profile))
    plan.checksum = plan.calculate_checksum()
    svc.journal.save_plan(plan)
    svc.create(plan.plan_id)
    with (
        patch(
            "venom_core.services.vast_environments.operations.inspect",
            return_value=inspection(),
        ),
        patch("venom_core.services.vast_environments.operations.tunnel") as tunnel,
        patch(
            "venom_core.services.vast_environments.operations.openai_ready",
            return_value={"runtime": "ready"},
        ),
        patch(
            "venom_core.services.vast_environments.operations.probe_gpu",
            side_effect=VastError("vast.gpu_probe_transport"),
        ),
        patch.object(OpenAIProbe, "benchmark") as benchmark,
    ):
        tunnel.return_value.__enter__.return_value = "http://127.0.0.1"
        result = workload(svc, plan.plan_id, "benchmark")
        benchmark.assert_not_called()
    assert result["status"] == "inconclusive"
    assert result["samples"] == []


@pytest.mark.parametrize(
    "env,minimum,version",
    [
        (
            [
                "CUDA_VERSION=12.8.1",
                "NVIDIA_REQUIRE_CUDA=cuda>=12.8",
                "SECRET=do-not-export",
            ],
            "12.8",
            "12.8.1",
        ),
        (["NVIDIA_REQUIRE_CUDA=cuda>=12.8 brand=tesla,driver>=570"], "", ""),
        (["CUDA_VERSION=garbage", "NVIDIA_DRIVER_CAPABILITIES=bad;id"], "", ""),
        ([None, "CUDA_VERSION", "CUDA_VERSION=bad\\nvalue"], "", ""),
        (None, "", ""),
    ],
)
def test_allowlisted_cuda_metadata(env, minimum, version):
    result = runtime_metadata({"config": {"Env": env}}, "sha256:" + "a" * 64)
    assert result["min_cuda"] == minimum
    assert result["cuda"] == version
    assert "do-not-export" not in json.dumps(result)


def test_nvcr_public_pinned_resolution_and_metadata():
    import hashlib

    config = json.dumps(
        {
            "architecture": "arm64",
            "os": "linux",
            "config": {"Env": ["CUDA_VERSION=13.0", "NVIDIA_REQUIRE_CUDA=cuda>=13.0"]},
        }
    ).encode()
    config_sha = "sha256:" + hashlib.sha256(config).hexdigest()
    manifest = json.dumps({"config": {"digest": config_sha}}).encode()
    sha = "sha256:" + hashlib.sha256(manifest).hexdigest()

    def respond(request):
        assert request.url.host == "nvcr.io"
        if request.url.path == "/proxy_auth":
            assert "authorization" not in request.headers
            assert request.url.params["scope"] == "repository:nvidia/pytorch:pull"
            return httpx.Response(200, json={"access_token": "registry-only"})
        assert request.headers["authorization"] == "Bearer registry-only"
        return httpx.Response(
            200, content=config if "/blobs/" in request.url.path else manifest
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = resolve_image("nvcr.io/nvidia/pytorch@" + sha, "arm64", client)
    assert result["image"] == "nvcr.io/nvidia/pytorch@" + sha
    assert result["runtime_metadata"]["min_cuda"] == "13.0"
    assert "registry-only" not in json.dumps(result)
    with httpx.Client(
        transport=httpx.MockTransport(Mock(side_effect=AssertionError))
    ) as client:
        with pytest.raises(VastError, match="concrete_image_tag_required"):
            resolve_image("vastai/pytorch:@vastai-automatic-tag", "arm64", client)
        with pytest.raises(VastError, match="invalid_public_image"):
            resolve_image("nvcr.io/other/private:tag", "arm64", client)


@pytest.mark.parametrize(
    "processor,expected",
    [
        ("100% GPU", {"cpu_percent": 0, "gpu_percent": 100}),
        ("100% CPU", {"cpu_percent": 100, "gpu_percent": 0}),
        ("30%/70% CPU/GPU", {"cpu_percent": 30, "gpu_percent": 70}),
        ("unknown", None),
    ],
)
def test_remote_processor_parser_and_interpreter(processor, expected):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            return Mock(returncode=0, stdout="/venv/main/bin/python\n")
        if len(calls) == 2:
            assert args[0] == "/venv/main/bin/python"
            return Mock(returncode=0, stdout='{"status":"passed"}')
        if args[0] == "nvidia-smi":
            return Mock(returncode=0, stdout="580.29.04\n")
        return Mock(
            returncode=0,
            stdout="NAME ID SIZE PROCESSOR\nmodel abc 1GB " + processor + "\n",
        )

    out = io.StringIO()
    with patch("subprocess.run", side_effect=run), contextlib.redirect_stdout(out):
        exec(
            REMOTE_SCRIPT,
            {
                "SELECT_SCRIPT": SELECT_SCRIPT,
                "CUDA_SCRIPT": "fixture",
                "ENGINE_MODE": "ollama",
                "MODEL_NAME": "model",
            },
        )
    result = json.loads(out.getvalue())
    assert result["ollama_processor"] == expected
    assert result["driver_version"] == "580.29.04"


def test_generated_ptx_and_interpreter_shell_are_valid():
    tree = ast.parse(CUDA_SCRIPT)
    assignment = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "ptx"
            for target in node.targets
        )
    )
    ptx = ast.literal_eval(assignment.value)
    assert b"\n.target sm_52\n" in ptx
    assert b"\\n" not in ptx
    assert (
        subprocess.run(["bash", "-n"], input=select_shell("vllm"), text=True).returncode
        == 0
    )
    out = io.StringIO()
    with (
        patch("sys.argv", ["select", "vllm"]),
        patch("shutil.which", side_effect=lambda value: value),
        patch(
            "subprocess.run",
            side_effect=[Mock(returncode=1), Mock(returncode=1), Mock(returncode=0)],
        ) as run,
        contextlib.redirect_stdout(out),
    ):
        exec(SELECT_SCRIPT, {})
    assert out.getvalue().strip() == "/venv/main/bin/python"
    assert run.call_count == 3


def test_wire_payload_uses_explicit_optional_fields(service):
    _, plan, _ = service
    probe = OllamaProbe(Mock(), plan.profile)
    body = probe._payload("text")
    assert "tools" not in openai_payload(body)
    body["format"] = "json"
    body["tools"] = [{"type": "function"}]
    body["messages"][0]["images"] = ["fixture"]
    value = openai_payload(body)
    assert value["response_format"] == {"type": "json_object"}
    assert value["messages"][0]["content"][1]["image_url"]["url"].endswith("fixture")


def test_provision_selects_image_base_instead_of_recreating_own_venv():
    assert "pytorch base <<" in select_shell("pytorch")
    out = io.StringIO()
    with (
        patch("sys.argv", ["select", "pytorch", "base"]),
        patch("shutil.which", side_effect=lambda value: value),
        patch("subprocess.run", return_value=Mock(returncode=0)) as run,
        contextlib.redirect_stdout(out),
    ):
        exec(SELECT_SCRIPT, {})
    assert "worker-venv" not in out.getvalue()
    assert run.call_count == 1
