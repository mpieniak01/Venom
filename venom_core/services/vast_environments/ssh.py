"""OpenSSH transport with explicit host trust, no agent forwarding or shells."""

from __future__ import annotations

import json
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import EnvironmentPlan

INSPECT_SCRIPT = """
import importlib.metadata, json, os, platform, shutil, subprocess
from pathlib import Path
def text(path):
    try: return Path(path).read_text()[:4096]
    except OSError: return None
def run(argv):
    try:
        p=subprocess.run(argv, capture_output=True, text=True, timeout=10)
        return p.stdout[:8192] if p.returncode==0 else None
    except (OSError, subprocess.TimeoutExpired): return None
def version(name):
    try: return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError: return None
disk=shutil.disk_usage('/workspace' if Path('/workspace').exists() else '/')
print(json.dumps({
  'schema_version':1, 'arch':platform.machine(), 'os':text('/etc/os-release'),
  'kernel':platform.release(), 'cpu_count':os.cpu_count(),
  'memory':text('/proc/meminfo'),
  'cgroup_memory_max':text('/sys/fs/cgroup/memory.max'),
  'cgroup_cpu_max':text('/sys/fs/cgroup/cpu.max'),
  'disk':{'total_bytes':disk.total,'free_bytes':disk.free},
  'mounts':run(['findmnt','-J','-o','TARGET,FSTYPE','/workspace']),
  'gpu':run(['nvidia-smi','--query-gpu=name,driver_version,memory.total,memory.used','--format=csv,noheader,nounits']),
  'packages':{n:version(n) for n in ['torch','transformers','vllm','numpy','ultralytics']},
  'ollama_version':run(['ollama','--version']),
  'process_manager':{'supervisor':bool(shutil.which('supervisorctl')), 'systemd':Path('/run/systemd/system').exists()},
  'startup_state':text('/workspace/venom-vast/startup.state'),
}))
"""


def ssh_args(
    plan: EnvironmentPlan, instance: dict, accept_new: bool = False
) -> list[str]:
    host = str(instance.get("ssh_host") or "")
    port = instance.get("ssh_port")
    if (
        not host
        or host.startswith("-")
        or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-:"
            for c in host
        )
    ):
        raise VastError("vast.invalid_ssh_host")
    try:
        port = int(str(port))
    except (TypeError, ValueError):
        raise VastError("vast.invalid_ssh_port") from None
    if not 1 <= port <= 65535:
        raise VastError("vast.invalid_ssh_port")
    if not Path(plan.ssh_identity_file).is_file():
        raise VastError("vast.ssh_identity_missing")
    known = Path(plan.ssh_known_hosts)
    known.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    return [
        "ssh",
        "-F",
        "/dev/null",
        "-p",
        str(port),
        "-i",
        plan.ssh_identity_file,
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "IdentityAgent=none",
        "-o",
        "BatchMode=yes",
        "-o",
        "ForwardAgent=no",
        "-o",
        "StrictHostKeyChecking=" + ("accept-new" if accept_new else "yes"),
        "-o",
        "UserKnownHostsFile=" + str(known),
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "ServerAliveInterval=10",
        "-o",
        "ServerAliveCountMax=2",
        "-o",
        "LogLevel=ERROR",
        "root@" + host,
    ]


def inspect(plan: EnvironmentPlan, instance: dict, accept_new: bool = False) -> dict:
    try:
        result = subprocess.run(
            ssh_args(plan, instance, accept_new) + ["python3", "-"],
            input=INSPECT_SCRIPT,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise VastError("vast.ssh_failed") from None
    if result.returncode:
        raise VastError("vast.ssh_failed")
    try:
        facts = json.loads(result.stdout)
        if not isinstance(facts, dict) or facts.get("schema_version") != 1:
            raise ValueError
    except ValueError:
        raise VastError("vast.inspect_invalid") from None
    expected = {"arm64": "aarch64", "amd64": "x86_64"}[plan.profile.cpu_arch]
    failures = []
    unknown = []
    if facts.get("arch") != expected:
        failures.append("cpu_arch")
    if facts.get("disk", {}).get("free_bytes", 0) < plan.profile.min_free_disk_bytes:
        failures.append("free_disk")
    if str(facts.get("startup_state") or "").strip() == "failed":
        failures.append("startup")
    memory = str(facts.get("memory") or "")
    memline = next((x for x in memory.splitlines() if x.startswith("MemTotal:")), "")
    try:
        memory_bytes = int(memline.split()[1]) * 1024
        cgroup = str(facts.get("cgroup_memory_max") or "").strip()
        if cgroup and cgroup != "max":
            memory_bytes = min(memory_bytes, int(cgroup))
        if memory_bytes < plan.profile.min_cpu_ram_mb * 1_000_000:
            failures.append("cpu_ram")
    except (ValueError, IndexError):
        unknown.append("cpu_ram")
    try:
        cores = float(facts["cpu_count"])
        quota = str(facts.get("cgroup_cpu_max") or "max").split()
        if quota[0] != "max":
            cores = min(cores, float(quota[0]) / float(quota[1]))
        if cores < plan.profile.min_cpu_cores:
            failures.append("cpu_cores")
    except (ValueError, KeyError, IndexError, ZeroDivisionError):
        unknown.append("cpu_cores")
    gpu = str(facts.get("gpu") or "").strip().splitlines()
    try:
        if len(gpu) != 1:
            raise ValueError
        # nvidia-smi reports MiB; API requirements use native MB.
        gpu_bytes = float(gpu[0].split(",")[2]) * 1024 * 1024
        if gpu_bytes < plan.profile.min_gpu_ram_mb * 1_000_000:
            failures.append("gpu_ram")
    except (ValueError, IndexError):
        unknown.append("gpu_ram")
    return {
        "ssh": "ready",
        "facts": facts,
        "capacity_status": "unsuitable" if failures else "inconclusive",
        "reasons": failures,
        "unknown": unknown,
        "note": "Read-only inspection is not a workload performance qualification.",
    }


@contextmanager
def tunnel(plan: EnvironmentPlan, instance: dict) -> Iterator[str]:
    args = ssh_args(plan, instance)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    target = args.pop()
    try:
        process = subprocess.Popen(
            args
            + [
                "-N",
                "-o",
                "ExitOnForwardFailure=yes",
                "-L",
                f"127.0.0.1:{port}:127.0.0.1:{8000 if plan.profile.mode == 'vllm' else 11434}",
                target,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        raise VastError("vast.ssh_failed") from None
    try:
        deadline = time.monotonic() + 20
        while True:
            if process.poll() is not None:
                raise VastError("vast.tunnel_failed")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise VastError("vast.tunnel_timeout") from None
                time.sleep(0.1)
        yield f"http://127.0.0.1:{port}"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
