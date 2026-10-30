"""Versioned startup: use the image runtime, never Docker inside Docker."""

import shlex

from venom_core.infrastructure.providers.vast.models import WorkloadProfile
from venom_core.services.vast_environments.runtime_scripts import (
    pytorch_script,
    vllm_script,
)

STARTUP_VERSION = "venom-vast-startup-v5"


def ollama_environment(profile: WorkloadProfile) -> dict[str, str]:
    return {
        "OLLAMA_HOST": "127.0.0.1:11434",
        "OLLAMA_CONTEXT_LENGTH": str(profile.context_tokens),
        "OLLAMA_NUM_PARALLEL": str(profile.max_parallel_requests),
        "OLLAMA_MAX_LOADED_MODELS": "1",
    }


def startup(profile: WorkloadProfile, *, download_model: bool = False) -> str:
    flock_command = "flock -w 120 9" if download_model else "flock -n 9 || exit 0"
    base = f"""#!/bin/bash
# {STARTUP_VERSION}
set -euo pipefail
umask 077
mkdir -p /workspace/venom-vast
exec 9>/workspace/venom-vast/startup.lock
{flock_command}
trap 'echo failed > /workspace/venom-vast/startup.state' ERR
echo provisioning > /workspace/venom-vast/startup.state
"""
    if profile.mode == "inspect":
        return base + "echo inspect_ready > /workspace/venom-vast/startup.state\n"
    base += "MODEL=" + shlex.quote(profile.model) + "\n"
    base += (
        "REQUIRED_BYTES="
        + str(profile.min_free_disk_bytes + int(profile.download_gb * 1_000_000_000))
        + "\n"
    )
    base += """FREE_BYTES=$(df -PB1 /workspace | awk 'NR==2 {print $4}')
test "$FREE_BYTES" -ge "$REQUIRED_BYTES"
"""
    if profile.mode == "vllm":
        return base + vllm_script(profile)
    if profile.mode == "pytorch":
        return base + pytorch_script(profile)
    for key, value in ollama_environment(profile).items():
        base += f"export {key}={shlex.quote(value)}\n"
    base += """command -v ollama >/dev/null
command -v curl >/dev/null
FREE_BYTES=$(df -PB1 /workspace | awk 'NR==2 {print $4}')
test "$FREE_BYTES" -ge "$REQUIRED_BYTES"
if ! curl --fail --silent --max-time 5 http://127.0.0.1:11434/api/version >/dev/null; then
  OLLAMA_HOST=127.0.0.1:11434 nohup ollama serve > /workspace/venom-vast/ollama.log 2>&1 9>&- &
  echo $! > /workspace/venom-vast/ollama.pid
fi
for i in $(seq 1 60); do
  curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/version >/dev/null && break
  sleep 1
done
curl --fail --silent --max-time 5 http://127.0.0.1:11434/api/version >/dev/null
"""
    if download_model and profile.download_gb > 0:
        base += 'ollama pull "$MODEL"\n'
    state = (
        "ready" if download_model or not profile.model else "awaiting_capacity_check"
    )
    return base + f"echo {state} > /workspace/venom-vast/startup.state\n"
