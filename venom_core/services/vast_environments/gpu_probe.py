"""Bounded CUDA execution probe; no installation, model pull or driver changes."""

from __future__ import annotations

import json
import subprocess

from venom_core.infrastructure.providers.vast.client import VastError
from venom_core.infrastructure.providers.vast.models import EnvironmentPlan
from venom_core.services.vast_environments.interpreters import SELECT_SCRIPT
from venom_core.services.vast_environments.ssh import ssh_args

# Executed in a child with a hard remote timeout. The tiny PTX kernel writes 42.
CUDA_SCRIPT = r"""
import ctypes as c, importlib.metadata, json, sys
def version(name):
    try: return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError: return None
result = {"status":"unavailable", "reason":"cuda_library_missing"}
ctx = module = None
memory = c.c_uint64()
try:
    lib = c.CDLL("libcuda.so.1")
    def call(name, types, *args):
        fn = getattr(lib, name)
        fn.argtypes, fn.restype = types, c.c_int
        code = fn(*args)
        if code:
            raise RuntimeError(str(code))
    P = c.c_void_p
    call("cuInit", [c.c_uint], 0)
    count = c.c_int()
    call("cuDeviceGetCount", [P], c.byref(count))
    if count.value != 1:
        raise ValueError("gpu_count")
    device = c.c_int()
    call("cuDeviceGet", [P,c.c_int], c.byref(device), 0)
    major, minor, driver = c.c_int(), c.c_int(), c.c_int()
    call("cuDeviceComputeCapability", [P,P,c.c_int], c.byref(major), c.byref(minor), device)
    call("cuDriverGetVersion", [P], c.byref(driver))
    name = c.create_string_buffer(128)
    call("cuDeviceGetName", [P,c.c_int,c.c_int], name, len(name), device)
    result.update(compute_cap=major.value*100+minor.value*10,
                  driver_cuda=str(driver.value//1000)+"."+str((driver.value%1000)//10),
                  gpu_name=name.value.decode(errors="replace"))
    ctx = P()
    call("cuCtxCreate_v2", [P,c.c_uint,c.c_int], c.byref(ctx), 0, device)
    ptx = b'.version 6.0\n.target sm_52\n.address_size 64\n.visible .entry probe(.param .u64 output) {\n.reg .u64 address;\n.reg .u32 value;\nld.param.u64 address, [output];\nmov.u32 value, 42;\nst.global.u32 [address], value;\nret;\n}'
    module = P()
    call("cuModuleLoadData", [P,P], c.byref(module), c.c_char_p(ptx))
    function = P()
    call("cuModuleGetFunction", [P,P,c.c_char_p], c.byref(function), module, b"probe")
    call("cuMemAlloc_v2", [P,c.c_size_t], c.byref(memory), 4)
    args = (P*1)(c.cast(c.pointer(memory), P))
    call("cuLaunchKernel", [P,c.c_uint,c.c_uint,c.c_uint,c.c_uint,c.c_uint,c.c_uint,c.c_uint,P,P,P],
         function,1,1,1,1,1,1,0,None,args,None)
    call("cuCtxSynchronize", [])
    value = c.c_uint32()
    call("cuMemcpyDtoH_v2", [P,c.c_uint64,c.c_size_t], c.byref(value), memory, 4)
    result.update(status="passed" if value.value==42 else "failed",
                  reason="kernel_verified" if value.value==42 else "wrong_result")
    if sys.argv[1] in {"pytorch","vllm"}:
        try:
            import torch
            result["torch_cuda"] = torch.version.cuda
            tensor = torch.ones((16,16), device="cuda")
            product = tensor @ tensor
            torch.cuda.synchronize()
            result["engine_kernel"] = "passed" if bool(torch.all(product==16).item()) else "failed"
        except ImportError:
            result["engine_kernel"] = "missing"
        except Exception:
            result["engine_kernel"] = "failed"
except OSError:
    pass
except RuntimeError as error:
    result.update(status="failed", reason="cuda_call_failed", cuda_error=int(str(error)))
except (ValueError, AttributeError):
    result.update(status="unavailable", reason="cuda_probe_unsupported")
finally:
    if memory.value:
        lib.cuMemFree_v2(memory)
    if module:
        lib.cuModuleUnload(module)
    if ctx:
        lib.cuCtxDestroy_v2(ctx)
result["python_executable"] = sys.executable
result["packages"] = {name:version(name) for name in ["torch","vllm","transformers","ultralytics"]}
print(json.dumps(result))
"""

REMOTE_SCRIPT = """
import json, re, subprocess, sys
def run(args, seconds=5):
    try:
        result=subprocess.run(args, text=True, capture_output=True, timeout=seconds)
        return result.stdout[:8192] if result.returncode==0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None
try:
    selected=subprocess.run([sys.executable,"-c",SELECT_SCRIPT,ENGINE_MODE],
                            text=True,capture_output=True,timeout=14)
    interpreter=selected.stdout.strip() if selected.returncode==0 else sys.executable
    result=subprocess.run([interpreter or sys.executable,"-c",CUDA_SCRIPT,ENGINE_MODE],
                          text=True,capture_output=True,timeout=25)
    probe=json.loads(result.stdout) if result.returncode==0 else {"status":"error","reason":"probe_process_failed"}
except subprocess.TimeoutExpired:
    probe={"status":"error","reason":"probe_timeout"}
except (ValueError, OSError):
    probe={"status":"error","reason":"probe_invalid"}
driver=run(["nvidia-smi","--query-gpu=driver_version","--format=csv,noheader"])
probe["driver_version"]=driver.strip() if driver and len(driver.splitlines())==1 else None
probe["ollama_processor"]=None
if ENGINE_MODE=="ollama":
    output=run(["ollama","ps"])
    rows=[row for row in (output or "").splitlines()[1:] if row.split() and row.split()[0]==MODEL_NAME]
    if len(rows)==1:
        gpu=re.search(r"([0-9]+)%\\s+GPU",rows[0])
        cpu=re.search(r"([0-9]+)%\\s+CPU",rows[0])
        mixed=re.search(r"([0-9]+)%/([0-9]+)%\\s+CPU/GPU",rows[0])
        if mixed:
            probe["ollama_processor"]={"cpu_percent":int(mixed[1]),"gpu_percent":int(mixed[2])}
        elif gpu:
            probe["ollama_processor"]={"cpu_percent":100-int(gpu[1]),"gpu_percent":int(gpu[1])}
        elif cpu:
            probe["ollama_processor"]={"cpu_percent":int(cpu[1]),"gpu_percent":100-int(cpu[1])}
print(json.dumps(probe))
"""


def probe_gpu(plan: EnvironmentPlan, instance: dict, accept_new: bool = False) -> dict:
    script = (
        "SELECT_SCRIPT="
        + repr(SELECT_SCRIPT)
        + "\nCUDA_SCRIPT="
        + repr(CUDA_SCRIPT)
        + "\nENGINE_MODE="
        + repr(plan.profile.mode)
        + "\nMODEL_NAME="
        + repr(plan.profile.model)
        + "\n"
        + REMOTE_SCRIPT
    )
    try:
        result = subprocess.run(
            ssh_args(plan, instance, accept_new) + ["python3", "-"],
            input=script,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise VastError("vast.gpu_probe_transport") from None
    if result.returncode or len(result.stdout) > 65536:
        raise VastError("vast.gpu_probe_transport")
    try:
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or data.get("status") not in {
            "passed",
            "failed",
            "error",
            "unavailable",
        }:
            raise ValueError
    except ValueError:
        raise VastError("vast.gpu_probe_invalid") from None
    return data
