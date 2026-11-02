# Remote Granite training

This manual operator workflow extends G01. Vast supplies a host; the job controller
uses an existing verified SSH connection and does not rent, stop or destroy instances.
No application startup, API request or CI job starts model training. Remote commands
are fixed RPC operations, not arbitrary command execution from a model or manifest.

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
