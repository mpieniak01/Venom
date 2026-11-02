# Gemma 4 operator: CPU preparation and remote qualification

This release prepares `google/gemma-4-12B-it` as a candidate for Venom's single
decision model. It does not load weights, train an adapter, execute tools or
activate the model. Actual training, tokenizer/mask qualification, GPU baselines,
checkpoint reload and candidate evaluation are deferred to an operator-requested
remote host session.

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
- An explicit trainability guard for this model: an HF repository name alone
  does not mean Venom has a qualified trainer for it.

The existing orchestration, policy and remote-training services remain the
integration points. The CPU evidence path does not implement a second executor.
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
| G4-02 one model across stages | Identity evidence implemented; autonomous orchestration qualification remains |
| G4-03 evaluation | CPU paired report implemented; independent benchmark and GPU baseline remain |
| G4-04 material | Canonical export/validation implemented; new G05 corpus and tokenizer masks remain |
| G4-05 remote SFT | Actual Gemma trainer/dependency lock and training deferred |
| G4-06 deployment | Candidate identity only; reload, promotion and activation deferred |
| G4-07 experiences | Eligibility contract implemented; automatic collection/replay remains |
| G4-08 DPO | Deferred until verified pairs and qualified remote training |
| G4-09/10 RL, full SFT, multimodal training | Conditional future remote experiments |

The local worker plan is maintained in the operator's ignored `docs_dev`
backlog. Public documentation contains the status of the shipped slice rather
than implying every training milestone is complete.

Use the existing [remote training lifecycle](REMOTE_TRAINING.md) and
[Vast startup/recovery procedure](PL/VAST_START_I_ODZYSKIWANIE.md) for subsequent
authorized remote work. The existing Granite worker must not be used for Gemma
by merely changing a model ID.

## Public protocol sources

- [Google Gemma 4 prompt format](https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4)
- [Google Gemma 4 tool calling](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4)
- [Google Gemma 4 12B IT checkpoint](https://huggingface.co/google/gemma-4-12B-it)

Profile updates must requalify serialization, metadata hashes, masks and runtime
evidence; source-document support is not a hardware qualification.
