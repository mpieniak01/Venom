"""Deterministic remote scripts; runtimes come from the pinned container image."""

import shlex

from venom_core.infrastructure.providers.vast.models import WorkloadProfile


def vllm_script(profile: WorkloadProfile) -> str:
    model = shlex.quote(profile.model)
    revision = shlex.quote(profile.model_digest)
    args = (
        f"python3 -m vllm.entrypoints.openai.api_server --model {model} "
        f"--revision {revision} --code-revision {revision} --host 127.0.0.1 --port 8000 "
        f"--gpu-memory-utilization {profile.gpu_memory_utilization} "
        f"--max-num-seqs {profile.max_parallel_requests} --max-model-len {profile.context_tokens}"
    )
    offline = "export HF_HUB_OFFLINE=1\n" if profile.download_gb == 0 else ""
    # No remote model code, public API port, image ENTRYPOINT assumption or driver installation.
    return (
        offline
        + f"""python3 -c 'import vllm, torch; assert torch.cuda.is_available()'
command -v curl >/dev/null
if ! curl --fail --silent --max-time 5 http://127.0.0.1:8000/health >/dev/null; then
  nohup {args} > /workspace/venom-vast/vllm.log 2>&1 9>&- &
  echo $! > /workspace/venom-vast/vllm.pid
fi
for i in $(seq 1 120); do
  curl --fail --silent --max-time 2 http://127.0.0.1:8000/health >/dev/null && break
  sleep 1
done
curl --fail --silent --max-time 5 http://127.0.0.1:8000/health >/dev/null
echo ready > /workspace/venom-vast/startup.state
"""
    )


def pytorch_script(profile: WorkloadProfile) -> str:
    imports = ["torch", "transformers"]
    if "vision" in profile.worker_tasks:
        imports += ["PIL", "ultralytics"]
    if "audio" in profile.worker_tasks:
        imports += ["faster_whisper"]
    setup = ""
    interpreter = "python3"
    if profile.worker_packages:
        interpreter = "/workspace/venom-vast/worker-venv/bin/python"
        constraints = (
            "import importlib.metadata as m; "
            + "names=['torch','torchvision','torchaudio','numpy']; "
            + "installed={d.metadata['Name'].lower():d.version for d in m.distributions()}; "
            + "print('\\n'.join(n+'=='+installed[n] for n in names if n in installed))"
        )
        setup = (
            "python3 -m venv --system-site-packages /workspace/venom-vast/worker-venv\n"
            + "python3 -c "
            + shlex.quote(constraints)
            + " > /workspace/venom-vast/base-constraints.txt\n"
            + interpreter
            + " -m pip install --disable-pip-version-check --only-binary=:all: "
            + "--constraint /workspace/venom-vast/base-constraints.txt "
            + " ".join(shlex.quote(package) for package in profile.worker_packages)
            + "\n"
        )
    code = (
        "import importlib,json; "
        + f"modules={imports!r}; "
        + "versions={name:getattr(importlib.import_module(name),'__version__',None) for name in modules}; "
        + "import torch; assert torch.cuda.is_available(); "
        + "print(json.dumps({'packages':versions,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0)}))"
    )
    return (
        setup
        + interpreter
        + " -c "
        + shlex.quote(code)
        + " > /workspace/venom-vast/worker.json\n"
        + "echo worker_ready > /workspace/venom-vast/startup.state\n"
    )
