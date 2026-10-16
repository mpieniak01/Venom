"""Versioned startup: use the image runtime, never Docker inside Docker."""

import shlex

from venom_core.infrastructure.providers.vast.models import WorkloadProfile
from venom_core.services.vast_environments.runtime_scripts import (
    pytorch_script,
    vllm_script,
)

STARTUP_VERSION = "venom-vast-startup-v2"


def startup(profile: WorkloadProfile) -> str:
    base = f"""#!/bin/bash
# {STARTUP_VERSION}
set -euo pipefail
umask 077
mkdir -p /workspace/venom-vast
exec 9>/workspace/venom-vast/startup.lock
flock -n 9 || exit 0
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
    if profile.download_gb > 0:
        base += 'ollama pull "$MODEL"\n'
    return base + "echo ready > /workspace/venom-vast/startup.state\n"
