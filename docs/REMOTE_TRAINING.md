# Remote Granite training

This manual operator workflow extends G01. Vast supplies a host; the job controller
uses an existing verified SSH connection and does not rent, stop or destroy instances.
No application startup, API request or CI job starts model training. Remote commands
are fixed RPC operations, not arbitrary command execution from a model or manifest.

## Host preparation and live progress

The native host helper is `scripts/remote_training_host/prepare.py`; the
[Polish operator runbook](PL/ZDALNY_TRENING.md#prosta-ścieżka-operatora) contains the
complete ordered workflow. For training plus Docker-based evaluation on one Vast
host, select a VM-capable offer and the official Ubuntu VM template, not the
generic Axolotl container. Follow the [startup/recovery checklist](PL/VAST_START_I_ODZYSKIWANIE.md).
On an already rented Linux amd64/NVIDIA SSH host,
prepare a clean reviewed checkout and invoke:

```bash
python3 /workspace/venom/scripts/remote_training_host/prepare.py \
  --code-root /workspace/venom --commit <REVIEWED_40_CHAR_SHA> --uv /usr/local/bin/uv
# Inspect the plan, then repeat with --apply.
```

Use an existing operator-installed `uv` to install managed Python 3.14.8, or pass
`--python /path/to/python3.14` instead. Apply creates a separate training venv,
installs both hash-locked requirements, probes the environment, downloads the
pinned model snapshot and initializes the host. It never rents or starts training.
It requires NVIDIA driver/nvidia-smi, setpriv, SSH, and sufficient free space.
`--offline-model` reuses a previously prepared, provenance/hash-verified snapshot.
No curl installer or application venv modification is involved.
The returned `remote_python` wrapper supplies the reviewed PYTHONPATH and model
interpreter; pass it to **every** SSH operation:

```bash
python scripts/remote_training.py --host gpu-training \
  --remote-python /workspace/data/remote-training/rpc-python \
  watch --run-id granite-remote-01 --interval 5 --max-seconds 3600
```

`watch` prints attempt/state/phase, optimizer steps, percentage and loss. Add
`--json-lines` for structured snapshots. One-shot `status` exposes the same
`progress` object. These are actual native worker observations from the current
attempt's bounded log, not simulated estimates. Unknown progress is null. 100%
means optimizer updates are complete; evaluation/checkpointing may still be
running. Only `status=succeeded` confirms completion. Ctrl+C, viewer timeout or
SSH failure disconnect the viewer without stopping training. Retry the viewer
after connectivity returns; use explicit `stop` to stop the job.

The first authorized real acceptance still needs host smoke, SSH disconnect,
checkpoint resume, collection and fresh local GPU verification. Do not equate
fixture tests or successful installation with GPU qualification or model quality.

## Evaluation sandbox preflight (CPU only)

Before GPU comparisons, load the exact frozen benchmark image on the selected
host and run:

```bash
cd /workspace/venom
/workspace/data/remote-training/rpc-python -m scripts.remote_training_host.check_sandbox \
  --cases /workspace/benchmarks/dialogue/manifest.json
```

Both writable and read-only checks must pass. This exercises Git ownership after
container export, including a root-operated VM, without loading CUDA or a model.
Replay trusted benchmark references on that host when available; CPU sandbox
qualification and training smoke are separate requirements.

## Runtime boundary

The generic `scripts/vast_training` image is Python 3.12/Axolotl. Granite uses the
existing native G01 encoder/worker and the qualified **Linux amd64 Python 3.14.8**
training lock. Do not run Granite through `text/completion`, or claim the generic
image is qualified. The SSH controller may use a different Python, but its trusted
host configuration selects the actual model interpreter and reviewed code checkout.
Install the training lock plus `requirements-remote-training-control.txt` together
in the separate model environment. Never update the application venv to do this.
`remote_env` checks installed versions/imports and pip check before model work.
A real host/GPU smoke is still required. Keep the requested 100 GB disk allocation;
preflight fails on inadequate space rather than silently changing the rental.

The GPU host needs the exact reviewed source checkout and local model snapshot
`ibm-granite/granite-4.2-3b` / `4e9c275e232f10211ec88644d106a1f6a1b60e06`.
Obtain weights through your existing Hugging Face procedure; neither pack nor RPC
uploads weights, tokens or credentials. Native workers use offline model loading.

## Prepare the host explicitly

Install only in the separate Python 3.14.8 model component, with matching CUDA/driver
and the exact source checkout (commands run on the prepared remote host):

```bash
/workspace/training-venv/bin/python -m pip install --require-hashes \
  -r requirements/locks/granite-operator-training-linux-py314.txt \
  -r requirements-remote-training-control.txt
PYTHONPATH=/workspace/venom /workspace/training-venv/bin/python \
  -m venom_core.services.remote_training.remote_env --code-root /workspace/venom
```

This does not create or update the application's environment. The component must
already have the required Python ABI; a Python 3.12 venv is rejected. Before updates,
the worker requires at least 10 GiB free for output; choose model-specific extra
capacity in addition to that floor. With this component ready:

```bash
PYTHONPATH=/workspace/venom /workspace/training-venv/bin/python -m venom_core.services.remote_training.cli host-init \
  --root /workspace/data/remote-training \
  --worker-python /workspace/training-venv/bin/python \
  --snapshot /workspace/models/4e9c275e232f10211ec88644d106a1f6a1b60e06 \
  --admission-db /workspace/data/runtime-admission.sqlite3 --code-root /workspace/venom
```

On a dedicated GPU machine use its shared host admission ledger. If other Venom
consumers exist, use their actual ledger, not a new namespace. The remote code must
be importable by the configured SSH Python (installed package or a private wrapper
that exports the reviewed `PYTHONPATH`). Keep SSH identities and host config separate
from job manifests. Configure an existing alias and verified host fingerprint;
StrictHostKeyChecking and BatchMode remain enabled.

## Pack admitted input locally

Use the qualified tokenizer component. Paths below are operator-provided local
paths; session data belongs under ignored `data/training/`, never the code folder.

```bash
python scripts/remote_training.py pack --run-id granite-remote-01 \
  --source /data/granite/pilot --manifest /data/granite/pilot/pilot-manifest.json \
  --profile config/granite_operator_profile.json \
  --snapshot /models/4e9c275e232f10211ec88644d106a1f6a1b60e06 \
  --output data/training/remote-01/input.zip --dataset domain --updates 100 --max-seconds 3600
```

Only the fixed domain/hf train+validation files, admitted data manifest and profile
are packed. The original provenance/licensing metadata is retained. No held-out
benchmark, raw chat, Git history or previous logs are included. Native input IDs
and labels are hashed locally and must match the remote encoder. Base, revision,
tokenizer/template, data, profile, code and lock form the portable identity;
host/GPU/boot/runtime qualification is separate. All source files are hash-verified.

## Upload, qualify, train and recover

Use the same connection options for all commands:

```bash
python scripts/remote_training.py --host gpu-training --ssh-config ~/.ssh/config upload --bundle data/training/remote-01/input.zip
python scripts/remote_training.py --host gpu-training start --run-id granite-remote-01 --stage smoke
python scripts/remote_training.py --host gpu-training status --run-id granite-remote-01
python scripts/remote_training.py --host gpu-training logs --run-id granite-remote-01
# Only after the matching native smoke PASS and explicit operator decision:
python scripts/remote_training.py --host gpu-training start --run-id granite-remote-01 --stage train
python scripts/remote_training.py --host gpu-training stop --run-id granite-remote-01
python scripts/remote_training.py --host gpu-training resume --run-id granite-remote-01 \
  --checkpoint attempts/0002/result/stages/train-first/checkpoint
```

Select the actual existing checkpoint from this run. Smoke continuation accepts
its completed 16-step first checkpoint and performs the four-step fresh reload;
it never silently resets the model. A run retains outputs in separate attempts.
Idempotent retries, atomic state/chunks and process-lifetime identities survive
SSH loss without spawning duplicate jobs. A host-wide GPU lock, shared admission
and a cumulative run time budget protect ownership. A timeout or stopped run is
not a success. GPU/model processes are reaped before ownership is released.

The 32+8 / 16+4 native smoke is required before full adapter training. Different
host/boot/GPU mapping, code, dependencies, data or profile requires qualification.
It checks assistant-only masks, frozen base, adapter updates, reload/resume and the
allowlisted tool-loop probe. It is a small real model run and is operator-requested,
not part of CI. The code checks the same G01 contract rather than forging a PASS.

## Collect and locally verify

```bash
python scripts/remote_training.py --host gpu-training collect --run-id granite-remote-01 \
  --output data/training/remote-01/result.zip --include-checkpoint
python scripts/remote_training.py inspect-result --input-bundle data/training/remote-01/input.zip \
  --bundle data/training/remote-01/result.zip
python scripts/remote_training.py import-result --input-bundle data/training/remote-01/input.zip \
  --bundle data/training/remote-01/result.zip --quarantine data/training/quarantine \
  --registry data/training/imported
```

The last command only quarantines: no implicit GPU reload or activation. To perform
a **fresh local GPU reload**, explicitly add `--verify-local --host-root LOCAL_HOST_CONFIG`;
optionally pass `--academy-models YOUR_ACADEMY_MODELS_DIR` for canonical Academy v2
metadata registration after verification. The local host must be offline and use
its actual shared ledger. Import never rewrites a foreign optimizer fingerprint
or authorizes local optimizer resume. No remote PASS file substitutes for the
live verifier. The active model and chat signature are not changed.

A result includes safetensors adapter/config, portable identity, profile/data
manifest, metrics, environment, qualification and logs. Full resume checkpoint is
optional at collection. Check hashes and the complete receipt, then retain a copy
outside the GPU host before an independently authorized provider destroy. Failed
runs remain collectable as incomplete evidence; a missing adapter is never success.
`export` of Vast metadata alone is not a model backup. Stopped rentals may retain
billable storage. Provider status/quote and cost are handled by the existing Vast
controller; training reports unmeasured cost explicitly instead of inventing it.


Collection preserves worker status separately from final supervisor status/exit code;
both must succeed before a bundle is complete. Partial bundles retain a bounded
coordinator log and, with --include-checkpoint, the latest saved stage checkpoint
with its original receipt. Live CLI logs also relay model stage output. Archives
and transfer files are private (0600), independently of umask. Quarantine uses
run_id/archive_sha256, so later attempts cannot replace earlier evidence and exact
retries reuse their directory. Local reload checks the data manifest hash and
probes the configured worker interpreter before acquiring GPU admission.

## Acceptance and limitations

Automated tests use fixture transports, harmless local subprocesses and model
doubles. They cover the offline cycle and corruption, wrong identity, partial
transfer, missing metrics, stale processes, reconnects, concurrency and quarantine.
These checks do not qualify a real GPU. First real acceptance is one authorized
short session with smoke, SSH disconnect, checkpoint resume, result collection
and fresh local reload, recording actual cost and host/runtime receipts.
Full model-quality evaluation on a frozen holdout follows separately.
This PR supplies adapter lifecycle, not training from random weights, multi-node
training, automatic rental/activation or an Academy UI redesign.

If an attempt fails before producing a checkpoint (for example GPU busy or
preflight rejection), retry explicitly with:

```bash
python scripts/remote_training.py --host gpu-training retry --run-id granite-remote-01 --from-attempt 1
```

Use the failed attempt number returned by status. The same retry token is
idempotent, retains prior evidence and never replenishes the run time budget.
Log offsets are logical byte positions across the bounded buffer; responses
include base_offset and truncated/reset flags when old bytes are unavailable
or an interrupted publication needs a cursor reset.

Operator data paths are checked before I/O. Use the current workspace, home,
temporary directory, /srv, /opt, /models, /mnt or /workspace. Parent traversal,
private credential/configuration directories and symlink ancestors are rejected.
The qualified Python path preserves its virtualenv spelling; model snapshot
aliases are accepted only when their resolved target remains in allowed data roots.
Local verification derives receipt.json beside its own request, regardless of
any output pathname in request content.

## Paired behavioral evaluation

After verified collection, use `python -m scripts.granite_operator.remote_comparison`
with the fixed local cases manifest, remote result path and confirmed adapter SHA.
Inference stays on the SSH GPU host; existing isolated Docker tools and oracles run
locally. See the [operator comparison workflow](PL/GRANITE_OPERATOR_EXPERIMENT.md#porównanie-adaptera-trenowanego-na-zdalnym-hoście).
This is separately operator-started evaluation, never an automatic training step.


### Configurable evaluation on one host

Use `python -m scripts.granite_operator.comparison` for a collected training result.
The process runs **model inference, Docker tools and independent oracles on the same
machine**. Invoke it locally, or invoke the same command inside an SSH session on
the training host. `--execution-host` records the operator-selected placement; it
does not provision a host or open SSH. The earlier `remote_comparison` command
remains a split local-tools/remote-model bridge and does not gain these flags.

```bash
source .venv/bin/activate
python -m scripts.granite_operator.comparison \
  --host-root /absolute/configured-host-root \
  --adapter-root /absolute/verified-result-directory \
  --expected-adapter-sha256 <sha256> \
  --cases /absolute/frozen-eval/manifest.json \
  --output /absolute/new-evaluation-directory \
  --execution-host local --concurrency 2 --batch-size 2
```

On a remote machine use its configured Python interpreter, paths, and
`--execution-host remote --concurrency 4 --batch-size 4`. Transfer the frozen
benchmark including its fixtures and pinned sandbox image first. The GPU host
must support the existing isolated Docker tools: an SSH container alone is not
sufficient. The command checks image availability before loading the model;
container startup must also support all existing sandbox restrictions. It never
falls back to executing tools without isolation or back on the local machine.
API/model services must be offline and host GPU admission must be available.

| Option | Default | Contract |
|---|---:|---|
| `--concurrency` | local: 1; remote: 4 | Active tasks: 1, 2, 4 or 8; one model instance throughout. |
| `--batch-size` | concurrency | Maximum same-arm requests in one GPU batch, from 1 to concurrency. |
| `--batch-wait-ms` | 20 | Wait to gather a batch: 0–100 ms. |
| `--task-seconds` | 60 | Per-task active budget: 1–600 s, excluding GPU queue waits. |
| `--max-seconds` | 7200 | Entire invocation including startup/queue time: 1–14400 s. |
| `--execution-host` | local | Placement label: local or remote; all components run on that host. |

Local execution defaults to one task (two can be selected). Remote execution
starts directly at four tasks with adaptive concurrency; it remains diagnostic
until correctness qualification. Generation and base/adapter switching have one
owner; each task retains a private workspace/container. Tune flags between runs,
using a new output directory. Exact resume (`--resume`) requires the same source,
benchmark, adapter, runtime versions, host identity and execution settings.

Trial receipts distinguish `task_seconds` (wall latency), `queue_seconds` and
`active_task_seconds`. Shared batch time is counted once in throughput summaries;
`execution-<run-id>.json` stores GPU batch duration, invocation wall time and shared
peak memory. Per-trial GPU peaks are null because memory belongs to the shared
session. Resumed invocation metrics cover only newly executed work.

Parallel runs remain diagnostic: `proposed_promotion_gate_passed` stays false.
Validate oracle verdicts against serial execution on the same host/profile before
adopting a parallel preset. Batch numerical differences and deadline effects can
change responses. Never compare a parallel loaded task latency directly with an
unloaded serial latency as a model promotion decision. No provider call or paid
qualification is part of automated tests; request each live run explicitly.


Remote concurrency policy: `--execution-host remote` defaults to four tasks and
adaptive operation. No serial warmup benchmark is required. `--no-adaptive` fixes
the selected limit. The model's short inference warmup still runs before timing.

- `--max-concurrency 8` bounds automatic growth (local adaptive default cap: 2).
- `--window-trials 16` selects the observation window, from 8 to 128 trials.
- `--low-gpu-percent 50` requires at least three sampled GPU utilization readings
  below the threshold before doubling concurrency.
- `--high-memory-percent 80` requires all sampled VRAM occupancy readings to be
  below this threshold as well. Missing/invalid telemetry never permits growth.
- Recoverable CUDA OOM lowers 4→2→1, preserves completed receipts, and retries
  only unfinished trials after worker threads stop and the allocator is cleared.
  Task/tool timeouts lower concurrency for the next window; timed-out trial
  results remain recorded. Other infrastructure/data errors abort for repair.
- A level that caused OOM/timeouts is blocked for the remainder of that invocation.
  GPU admission, host retention and diagnostic-only promotion rules still apply.

Decisions are flushed immediately to `concurrency-decisions.jsonl`. Each trial
records its actual `execution_concurrency` and `execution_batch_size`; execution
metrics include sampled GPU/VRAM occupancy and the decision history. Batch size
scales with concurrency while preserving its initial ratio. Adaptation occurs
between windows, never by changing adapter state from concurrent task threads.


See [independent training milestones](REMOTE_TRAINING_MILESTONES.md) for separately runnable 80/125/160 training stages, historical result collection and dialogue evaluation.
