# Host runtime admission (API v1)

`venom_core.services.runtime_admission` is the public ownership contract for
optional modules. It contains no laboratory runner, model, scenario, or UI.

## Qualification and startup

Set `RUNTIME_ADMISSION_ENABLED=true` **before starting the API** when enabling an
experiment requiring host-wide exclusivity. Default `false` retains regular
Venom behavior: hooks create no ledger/lock files, and experimental `acquire`
returns `runtime_admission_disabled`. The laboratory has its own independent
`FEATURE_COOPERATION_LAB=false` default.

Supported topology: **one Linux API process, one host runtime namespace**. A
lifetime OS `flock` on `runtime-admission.host.lock` refuses a second API process,
including programmatically configured workers. `WEB_CONCURRENCY` and
`UVICORN_WORKERS` values other than `1` are explicitly unsupported. Other OSes
with admission enabled return `runtime_topology_unsupported`. This concerns the
Venom backend, not the Windows Codex application or its tools.

The ledger is `runtime-admission.sqlite3` under `MEMORY_ROOT`; relative roots
are anchored at the source repository, not the caller's working directory.
Mutations respect `ensure_data_mutation_allowed`. The ledger and host lock are
private files (`0600`); a newly created ledger directory is `0700`. Existing
parent-directory permissions remain unchanged. Symbolic links in the ledger path,
non-regular files and hard-linked ledgers are rejected as `runtime_storage_unsafe`;
read-only observations fail closed without modifying those paths. It stores one lease and
at most 128 current/uncertain operation rows (then fail closed until recovery): no prompts, generated text, credentials or
weights. Read-only snapshots create no file, execute no DDL, and work when
mutations are forbidden. Independent direct daemon clients, another installation
with another ledger, and independent GPU workloads are not a qualified exclusive
topology. Admission must be enabled before any consumer starts.

## Public interface

```python
from venom_core.services.runtime_admission import get_runtime_admission

admission = get_runtime_admission()
lease = admission.acquire(
    owner="cooperation_lab", run_id=host_run_id,
    engine=validated_engine, model=immutable_model_reference,
)

async def lifecycle():
    await asyncio.to_thread(adapter.load)
    try:
        return await asyncio.to_thread(adapter.generate)
    finally:
        await asyncio.to_thread(adapter.close)

await lease.run(lifecycle, confirm_quiescent=adapter.is_quiescent)
assert lease.release()
```

Owner, validated model/runtime selection, run ID and lease are host capabilities,
never values delegated to model output or arbitrary browser owner/token fields.
Store public identity only, never the private token. Adapter load/generate use
`with lease.operation(kind="load")` / `with lease.operation():`. Close uses:

```python
with lease.cleanup(confirm_quiescent=self.is_quiescent):
    self.close_owned_worker()  # Owned child only: signal, synchronize and join.
```

A lifecycle delegates one actual operation to its own thread. Two concurrent
generations are refused. Context-manager enter/exit must occur in the same
execution context; do not enter in a load thread and exit in a different thread.
Cleanup is permitted after cancel/quarantine and cannot admit generation. Its
quiescence check also runs when the cleanup body raises: a verified joined worker
clears owned quarantine while preserving that error; an unconfirmed worker remains
quarantined.

`cancel()` prevents subsequent work; it does not terminate a worker or release
ownership. `run(factory)` retains a strong reference to its shielded worker, so
cancelling its HTTP waiter does not release the resource. The factory must await
real child/thread completion. Cancelling an unshielded `to_thread` coroutine
cannot establish thread completion. Adapter token/step/cleanup budgets and actual
CUDA/process completion remain mandatory; socket closure is insufficient.

`release()` is idempotent, returns `False` during active work/quarantine and
rejects foreign capabilities. No TTL frees a lease. A terminal model failure
with a trusted joined/synchronized verifier releases normally. Unknown worker
or transport completion quarantines the resource. Caught nested errors remain
visible to admission rather than silently permitting another experiment.

A terminal HTTP rejection observed by the guarded transport **before yielding
any generation response** carries typed proof bound to that exact operation.
Only HTTP 400/401/403/404/405/413/415/422 qualify; the original HTTP error still
reaches the caller, but rejected work does not leave an orphan admission row.
A status/message raised by a caller or replayed from another operation is not
proof. HTTP 408/409/429/5xx, timeouts and errors after an accepted 2xx response
retain quarantine. Error diagnostics sample at most 2048 bytes for 250 ms and
retain fixed reason codes, a prefix hash and size/completeness metadata; raw
upstream body is not copied into the normal-chat trace/browser error.

`lease.recover(confirm_quiescent=host_probe)` or host-admin
`admission.recover(confirm_quiescent=host_probe)` requires a trusted callback.
A UI flag, deadline, closed socket, loaded-model list or `empty_cache()` is not a
verifier. Live local operation rows cannot be erased. Process crash releases
the OS lock but leaves ownership/work rows durable. Restart reports quarantine,
requires actual daemon/worker quiescence and never auto-resumes experiments.

Conflicts expose stable `RuntimeAdmissionError.code` / HTTP detail `code`; the
caller translates its UI. `snapshot()` reports availability, owner/run/engine/
model and active-operation count, without the private token.

## Host consumer map

| Consumer | Admission boundary |
| --- | --- |
| Agent chat, Council, skills | MAF completion and stream |
| Simple chat and voice | Existing `runtime_request_guard`, enclosing actual stream |
| Native Ollama | Agent-loop call and operator fallback |
| Summary, translation, local vision and probes | Traffic-controlled local generation/completion/embedding HTTP routes; health/catalog and unrelated HTTP remain available |
| In-process ONNX LLM | Actual generation iterator and close |
| LLM benchmark | Start and full background worker, including direct HTTP streaming |
| Coding benchmark | Reservation before thread creation; real scheduler worker lifetime |
| Model/adapter activation | ModelManager, ModelRegistry and model-switch route |
| Runtime switch/start/stop/restart | Activation routes, LlmServerController and LLM RuntimeController services |
| Eviction / daemon profile | Resource-release, Ollama single-model policy, benchmark preflight and profile mutation |

Training, independent non-LLM GPU vision, remote Vast workloads and external
shell/CLI activity are not serialized here. Experiments must budget resident
RAM/VRAM and fail clearly rather than changing the chat model, downloading
weights, killing unrelated work or assuming an empty GPU. No global chat timeout,
selection, inference defaults or model weights are changed.

## Verification and rollback

Tests exercise real `asyncio.to_thread` lifetime, cancellation/late completion,
cleanup, foreign capabilities, real second-process refusal/crash, durable
recovery, read-only observation and existing host entrypoints. No hardware or
robot actuation is part of unit tests.

Rollback: reconcile/stop the owned experiment, disable its module and admission,
then restart the API. Retain the ledger until owned GPU/worker completion is
verified; deleting it must never make active/uncertain work appear free.
