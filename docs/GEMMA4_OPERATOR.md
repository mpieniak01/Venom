# Gemma 4 operator: explicit variants and GPU training

This release supports `google/gemma-4-E4B-it` and `google/gemma-4-12B-it`
as explicitly selectable decision models and
adds an opt-in execution path through Venom's existing guarded runtime. Model
selection remains available for chat and other tasks. One selected model can
conduct a task without requiring separate classifier, planner or critic models;
Gemma is not a global model lock.

Actual remote training and attachment/activation of a produced adapter are
**separate operator tasks**. This release does not load Gemma weights, certify a
Gemma tool loop or activate any adapter. Tokenizer/mask qualification, GPU
baselines, checkpoint reload and candidate evaluation remain remote work.

## What is available

- A revision-pinned model/loader profile with hashes of the configuration,
  tokenizer, processor and chat template.
- Native tool-call parsing with schema validation and rendering delegated to the
  supplied model chat-template implementation.
- CPU export of canonical dataset splits, preserving selected assistant turns
  and excluding context-only failed demonstrations from supervision.
- Dataset group/content leakage checks and eligibility checks for independently
  verified experience records.
- Runtime evidence comparison across task stages, without claiming GPU readiness.
- Paired diagnostic trial comparison with explicit arm identities and timing on
  shared correctly completed cases.
- An immutable material release that excludes raw holdout records from the
  training payload and binds the payload to the pinned profile.
- An offline sample benchmark with independent filesystem verification and a
  bounded in-process reference executor.
- Explicit export of redacted, reviewed experiences backed by separate evidence
  bytes, with reviewed assistant-turn selection.
- Opt-in `single_model` task dispatch using the selected registered service,
  existing tool guards and authoritative native tool history.
- An explicit trainability guard for this model: an HF repository name alone
  does not mean Venom has a qualified trainer for it.

The existing orchestration, policy and remote-training services remain the
integration points. The CPU preparation path does not implement a second agent executor.
A matching runtime identity is not evidence of a completed tool loop or a trained
model.

## Commands

Run from the repository root with the project environment active. The optional
control dependency is declared in `requirements-gemma4-operator-control.txt`.
The feature imports no Torch/Transformers model runtime during CPU preparation.

```bash
source .venv/bin/activate
python -m pip install -r requirements-gemma4-operator-control.txt
python scripts/gemma4_operator.py plan
```

The profile defaults to `config/gemma4_operator_profile.json`. Its revision and
metadata hashes are public checkpoint metadata; they do not certify weight
bytes or a locally installed snapshot. To verify an explicitly materialized
snapshot's declared metadata files:

```bash
python scripts/gemma4_operator.py verify-snapshot \
  --snapshot data/training/gemma-snapshot \
  --output .venom_runtime/gemma4/snapshot-evidence.json
```

Inputs and evidence outputs are constrained to repository data/training and
.venom_runtime/gemma4. Profiles may also be read from repository config.
An operator can explicitly approve an additional absolute root with
GEMMA_OPERATOR_DATA_ROOT (for example an isolated mounted remote workspace).
Symlinked files and parent directories, traversal outside the approved roots and
non-JSON input/output files are rejected. Store a materialized model snapshot
inside an approved data root before verifying it.

Existing evidence outputs are never overwritten. Use a new output path for
each run. This check rejects symlinked files; a Hugging Face cache snapshot must
first be deliberately materialized.

### Material preparation

The input is one JSON object mapping split names to lists of canonical
`messages`/`tools` records. Source G01–G04 data and their historical manifests
are immutable. Do not concatenate retained versions as independent corpora.

```bash
python scripts/gemma4_operator.py prepare-material \
  --input data/training/gemma-source-splits.json \
  --output data/training/gemma-candidate/material.json
```

The result retains the record targets and a provenance/validation manifest.
It is explicitly not tokenized and not training-ready. A remote qualification
must prove token boundaries, selected-turn masks, EOS and packing with the exact
pinned Gemma tokenizer. A generic assistant-only loss setting is insufficient
for the context-only failed assistant turns in our material.

An experience record needs explicit training consent, redaction, approved review
and a transcript-bound verifier receipt. The model's own success statement is
not such a receipt. No private records or transcripts belong in Git.

### Immutable release and benchmark reference

`freeze-material` validates the same source splits and publishes an immutable
release containing **train and validation only**. A supplied holdout contributes
only its count and hash. Keep the raw reserve separate from remote training
uploads. This does not turn a historical or synthetic reserve into an independent
final benchmark.

```bash
python scripts/gemma4_operator.py freeze-material \
  --input data/training/gemma-source-splits.json \
  --output data/training/gemma-candidate/release.json
python scripts/gemma4_operator.py qualify-cases \
  --manifest config/gemma4_operator_benchmark/manifest.json \
  --output .venom_runtime/gemma4/reference-qualification.json
```

The bundled cases are a small synthetic example, not the final evaluation set.
`qualify-cases` checks inventory hashes, executes reference actions in a fresh
temporary workspace and independently compares resulting files with expected
state. The built-in executor supports only the declared in-process fixture
operations; it runs no shell, model or network calls. A supplied Python executor
is trusted code, not an OS sandbox, and does not receive reference actions or
expected results. `REFERENCE_PASS` verifies the fixtures/reference path, never
model accuracy or promotion. Reference failures exit with code 3.

### Selected-model execution

The task API accepts the following optional fields:

```json
{
  "content": "Inspect the current service status and explain the evidence.",
  "agent_mode": "single_model",
  "model_service_id": "local"
}
```

`agent_mode` defaults to `auto`, preserving the existing routes and model chooser.
`model_service_id` is an existing kernel service identifier, not a model name,
URL or new provider configuration; omit it to use the currently selected default
service. Supplying it in `auto` mode is rejected. Switch models through the
existing model configuration/chooser; this path records the actual service/model
used for the task. Forced provider/tool shortcuts are rejected in `single_model`
mode rather than silently ignored.

This mode currently accepts text only. Requests with images or a preferred
language outside `pl/en/de` are rejected. It retains stored session history and
summary but skips generating a new summary, retrieval-model memory enrichment
and lesson enrichment. The selected model receives a fixed language instruction;
a separate translator is not invoked. Completion preserves raw session history
and status without embedding-backed memory upserts, automatic lessons or legacy
LLM-only learning-log entries. Usage is recorded as `SelectedModel`. Reviewed
experience export remains the explicit route into training material. The `auto`
path keeps its existing preprocessing and postprocessing.

Function calling starts disabled for this path. After separately qualifying the
exact service/model tool loop, an operator may list its exact `service_id|model_id`
in `SINGLE_MODEL_TOOL_CALLING_ALLOWLIST`. This setting is a qualification
attestation, not an automatic probe. An unlisted service can answer in text but
is not given tools. Existing runtime permission checks still apply to each
invocation; model proposals are not permission grants.

The path uses the existing MAF service and a 30-second execution budget. It
records canonical native calls/results in `context_history.gemma4_operator`.
Failures, cancellation and incomplete capture cannot qualify an experience.
There is no automatic retry of a possibly completed operation. Durable resume
and exactly-once recovery are not claimed by this release.

### Reviewed experience export

Export is an explicit CPU step; a successful task is not automatically a training
sample:

```bash
python scripts/gemma4_operator.py export-experience \
  --task data/training/experience/task.json \
  --receipt data/training/experience/review.json \
  --evidence data/training/experience/replay-evidence.json \
  --output data/training/experience/eligible-record.json
```

The source must be a completed saved task with a complete canonical runtime
trace. The receipt must contain:

- `schema_version: 1`, matching `task_id`, canonical `source_task_sha256`,
  `training_consent: true`, `environment_revision`, `record_id`,
  `problem_group` and `language`;
- `redaction` with `status: "reviewed"`, `source_trajectory_sha256`, and a
  `trajectory` containing exactly `messages` and `tools`;
- `review` with `status: "approved"`, a human reviewer identity,
  `trajectory_sha256` and nonempty `selected_assistant_indices`;
- `verification` with `status: "passed"`, `verifier`,
  `trajectory_sha256` and SHA-256 of the separate evidence file.

Canonical hashes use sorted-key compact UTF-8 JSON (see `material.digest`).
The evidence JSON identifies the same task, trajectory and verifier, declares
`kind: "independent_replay"`, `status: "passed"` and includes nonempty named
`checks`, each with `passed: true`. The command hashes the actual evidence
bytes. An external trusted runner must perform that replay; this exporter checks
supplied evidence and does not authenticate its author.

Redaction cannot invent calls or change the tool catalog. Review can select a
subset of original eligible assistant turns; other turns remain context only.
An explicit source training prohibition or evaluation-only split is not
overridden by a receipt. Rejected exports exit with code 4, retain safe reason
codes and omit raw text and training records. No private tasks, receipts or
transcripts belong in Git.

### Runtime evidence

Supported runtime precisions are `bf16` and `nf4`. A request JSON contains exactly `precision`, `backend`, `backend_version` and
`artifact_sha256`. Model, revision, loader, context and metadata hashes come from
the pinned profile. Observation input contains `identity` including `enable_thinking` and optional
`stages`, each with a `stage` name and the same identity fields.

```bash
python scripts/gemma4_operator.py readiness \
  --request data/training/gemma-runtime-request.json \
  --observed data/training/gemma-runtime-observed.json \
  --output .venom_runtime/gemma4/runtime-evidence.json
```

Omitting `--observed` returns a prepared expectation. Mismatching evidence exits
nonzero and records the mismatch. Consistent supplied evidence still reports
activation, GPU and tool-loop qualification as false. Artifact hashes in an
observation are attestations from the caller; this command does not inspect
remote weight files or authenticate a remote process.

### Diagnostic comparison

`compare` consumes a JSON object with `identities` (base and adapter) and
`trials`. Both arms must declare the same model/revision, effective precision,
runtime, context, decoding limits, seed, tool/evaluator/benchmark/tokenizer/template hashes and concurrency.
The adapter arm additionally identifies the adapter. Each case must have one
trial per arm; failures and timeouts remain in the report.

```bash
python scripts/gemma4_operator.py compare \
  --input data/training/gemma-comparison-input.json \
  --output data/training/gemma-candidate/diagnostic-comparison.json
```

An infrastructure failure retains the report but exits with code 3; a runtime
identity mismatch exits with code 2; malformed input exits with code 1.

This CPU aggregation cannot authorize promotion. Actual measurements require a
separately qualified runner, independent tasks and verifier evidence. Compare
serial and parallel behavior on a fixed subset before using parallel trials for
candidate selection.

## Delivery and deferred work

| Plan area | State after this release |
|---|---|
| G4-01 identity and protocol | CPU contracts implemented; native GPU cycle deferred |
| G4-02 selected-model execution | Opt-in guarded dispatch and native history implemented; Gemma GPU tool-loop and durable resume qualification remain |
| G4-03 evaluation | Shared GPU comparison runner supports both variants and images; independent final benchmark and measured baselines remain |
| G4-04 material | Canonical validation and immutable release with separate reserve implemented; G05 V2 and native masks qualified for both variants |
| G4-05 remote SFT | Both native GPU loaders and LoRA/QLoRA workers implemented; real host qualification and training require an authorized session |
| G4-06 deployment | Candidate identity only; reload, promotion and activation deferred |
| G4-07 experiences | Explicit reviewed export from complete runtime traces implemented; independent replay execution remains external |
| G4-08 DPO | Deferred until verified pairs and qualified remote training |
| G4-09/10 RL, full SFT, multimodal training | Conditional future remote experiments |

The local worker plan is maintained in the operator's ignored `docs_dev`
backlog. Public documentation contains the status of the shipped slice rather
than implying every training milestone is complete.

Use the existing [remote training lifecycle](REMOTE_TRAINING.md) and
[Vast startup/recovery procedure](PL/VAST_START_I_ODZYSKIWANIE.md) for subsequent
authorized remote work. The existing Granite worker must not be used for Gemma
by merely changing a model ID.


## Two model variants and GPU experiments

| Variant | Explicit Ollama name | Profile | Native loader / layers |
|---|---|---|---|
| E4B IT | `gemma4:e4b` | `config/gemma4_operator_e4b_profile.json` | `Gemma4ForConditionalGeneration` / 42 |
| 12B IT | `gemma4:12b-it-q4_K_M` | `config/gemma4_operator_profile.json` | `Gemma4UnifiedForConditionalGeneration` / 48 |

Ollama remains the application inference runtime; the operator keeps model choice.
Chat, model cards, voice, benchmarks and Academy show explicit variant names.
A moving legacy Gemma alias resolves only from a unique matching complete
manifest digest and architecture/precision metadata. Without this proof it is
read-only diagnostic state and cannot activate a model. Other providers remain
selectable. The local explicit E4B tag preserves the previously observed E4B
manifest; creating a tag does not retrain or convert its weights.
Each experiment binds its explicit tag/digest to a separately pinned training
checkpoint. Vendor GGUF metadata alone does not prove an HF revision. Merge an
adapter into its exact training base before conversion/import; arbitrary vendor
blob adapter injection remains unqualified.

Training, generation and adapter evaluation require GPU. CPU/disk offload and
silent precision/model changes are rejected. Metadata and dataset validation do
not load the inference model. The initial host search uses at least 24 GB VRAM, 32 GB instance RAM and 100 GB disk;
capacity and throughput require remote measurement. In particular, 12B BF16 LoRA
may require a larger GPU; never silently switch precision.

G05 V2 is private at `data/training/gemma-g05-v2-20261103-ready/`:
832 training, 224 validation and 160 diagnostic holdout conversations.
It retains G04 unchanged and adds 288 executed PL/EN demonstrations of four
real FileSkill functions across six families. These authored scenarios are not
human-reviewed production incidents or coverage of every Venom tool.
An independent 24-case reserve checks summary, translation and image behavior
with diagnostic lexical oracles. Audio retention remains unqualified.

Both native tokenizers separately encoded all 1,056 train/validation records.
Excluded turns retain labels -100; native continuation turns receive no invented
EOS. Packing is disabled; oversize records fail. For this text corpus the vectors
happen to match, while model/loader/template/processor identities remain separate.

### Preparation

Existing outputs are immutable. Keep material, proofs and bundles outside Git.

```bash
source .venv/bin/activate
python scripts/gemma4_operator.py prepare-corpus \
  --source-root data/training/granite-g04-material-20261102 \
  --destination data/training/gemma-g05-next

python scripts/gemma4_operator.py prepare-session \
  --profile config/gemma4_operator_e4b_profile.json --precision nf4 \
  --source-root data/training/gemma-g05-v2-20261103-ready \
  --input data/training/gemma4-dual-training-ready-20261103/e4b-it/encoded.json \
  --binding data/training/gemma4-dual-training-ready-20261103/e4b-it/ollama-binding.json \
  --snapshot data/training/gemma4-e4b-native-metadata-20261103 \
  --destination data/training/gemma-session-e4b-qlora-next \
  --evaluation-cases data/training/gemma4-retention-v2-20261103-ready/manifest.json \
  --run-id gemma-e4b-qlora-pilot --max-updates 125 --max-seconds 3600
```

Use `bf16` for LoRA and the 12B profile/snapshot for 12B. These are four
independent choices, not automatically scheduled jobs. Budgets are explicit
pilot settings. `encode-material --profile ... --input release.json --snapshot
... --output encoded.json` performs native encoding after `freeze-material`.
`bind-ollama` validates explicitly supplied selection and observed metadata.

Session preparation verifies canonical data, encoding, binding, recipe, actual
source hashes and dependencies. Its training ZIP contains only recipe,
encoded train/validation and binding: no holdout, retention answers or weights.
Freeze code before final packaging. Optional report `--output` must be outside
the self-publishing destination and is checked before any artifact creation.

### Authorized remote session

1. Select variant/method and approve the provider run and monetary budget.
2. Use the existing host bootstrap with `--model-profile` and separate roots/
   snapshots per variant; share the qualified interpreter and admission ledger.
   Setup only occurs with explicitly requested `--apply`.
3. Upload `input.zip` and `evaluation.zip` separately with the existing
   `scripts/remote_training.py --host <alias> --remote-root <variant-root>
   --remote-python <qualified-wrapper> upload --bundle <archive>` command.
   Use the same variant root and wrapper for both. Evaluation extracts to
   `<variant-root>/runs/<evaluation.remote_run_id>/input/<manifest_relative>`,
   using the two fields in `preflight.json`; pass that manifest to comparison
   `--cases`. The evaluation run is staged only and must not be started as training.
   Materialize the exact pinned model weights.
4. Run native GPU environment preflight. Check full CUDA placement and measured
   memory before tuning batch/concurrency.
5. Qualify first/resume smoke with sealed evidence from both stages. Use its
   adapter result for paired tool-loop and retention checks; the base arm disables
   the adapter. The comparison runner requires an existing adapter result.
6. Train/resume within budget, seal and collect using the existing supervisor.
7. Compare each final adapter with its own base and matched precision/case identities.
8. Separately collect comparison trials, progress and summaries with hashes;
   adapter collection does not include those output directories.
9. Verify downloaded artifacts before any operator-requested host removal.

Failures retain the host and checkpoints. Attachment/activation is a separate
operator task. Source preparation and mock tests do not certify GPU performance
or model quality. The existing shared hash lock includes the exact vision
dependency closure as well as Torch, Transformers and PEFT.

## Public protocol sources

- [Google Gemma 4 prompt format](https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4)
- [Google Gemma 4 tool calling](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4)
- [Google Gemma 4 12B IT checkpoint](https://huggingface.co/google/gemma-4-12B-it)

Profile updates must requalify serialization, metadata hashes, masks and runtime
evidence; source-document support is not a hardware qualification.

### First pilot host selection

```bash
source .venv/bin/activate
python scripts/cloud/vast/offers_table.py --training-suite config/gemma4_pilot_host.json
```

This uses the native VM workflow rather than the standalone Axolotl container kit.
Start with separate QLoRA pilots for E4B IT and 12B IT (125 updates, at most
3600 seconds each). Qualify GPU first/resume smoke before either training.
Compare each adapter to its own base on the frozen domain diagnostic cases as
well as the separate retention reserve; record task correctness, tool-call
validity, completion time and failures. The packaged retention reserve alone
does not establish improvement in Venom maintenance tasks.

Collect and hash-check adapters, exact base/revision and tokenizer/processor
identities, receipts and comparison outputs. Local acceptance on the 12 GB RTX
3060 is a separate GPU-only load/generation check in Ollama after merging each
adapter with its exact training base and conversion to the intended GGUF
quantization. Neither this pilot nor vendor GGUF metadata proves arbitrary
adapter injection compatibility. Preserve existing models until acceptance.

### Bootstrap interpreter and image inference

Run host preparation through managed Python 3.14.8, including the bootstrap
controller. Ubuntu VM system Python 3.10 cannot validate native snapshot hashes
(`hashlib.file_digest`). After installing the verified uv executable, use
`uv run --no-project --python 3.14.8 python scripts/remote_training_host/prepare.py`
with the selected profile and normal plan/apply arguments. A snapshot directory
must be named with the pinned revision SHA, not a friendly variant alias.

Image generation uses CUDA BF16 autocast: NF4 leaves vision LayerNorm weights
in FP32, including the 12B Unified patch embedder. Casting processor pixels
alone does not qualify this mixed-precision path. A failed image evaluation can
be rerun under a new output identity without repeating a sealed text training.
