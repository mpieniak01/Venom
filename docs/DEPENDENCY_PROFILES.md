# Dependency profiles: Python 3.14 candidate

The canonical policy is `config/dependency-profiles.json`. This candidate targets
Linux x86_64, Python **3.14.8** (`platform.python` is the minor `3.14`;
`python_target` records the exact interpreter). Inputs and lock paths use `py314`.
These declarations do not establish installation, runtime or security qualification.
The existing Python 3.12 evidence does not qualify the new interpreter or graph.

## Seven managed profiles

| Profile | Kind | Dependency boundary |
| --- | --- | --- |
| `light` | Application | MAF core, API, orchestration and the selected application clients; no local model engines. |
| `ci` | Application | Extends Light with the shared test, lint and audit tools. |
| `build` | Component | Pinned pip/setuptools/wheel/packaging toolchain used by explicit bootstrap; not a model environment. |
| `full` | Application | Extends Light with actual memory, vision, web/documents, desktop, hardware and CUDA voice/floor consumers. |
| `full-ci` | Application | Extends Full with the same CI tools; its installed inventory is distinct from exact Full. |
| `multi-runtime-cuda` | Component | Independent minimal API/model/audio/OCR base for the CUDA daemon; does not extend Light. |
| `granite-operator-training` | Component | Shared isolated CUDA training dependencies for Gemma 4 and FunctionGemma; historical lock name retained for checkpoint compatibility. |

The five compatibility inputs `requirements.txt`, `requirements-runtime-common.txt`,
`requirements-docker-minimal.txt`, `requirements-profile-api.txt` and
`requirements-profile-web.txt` continue to represent Light. Generated SCM inputs
are self-contained and contain no recursive `-r` or `-c` directives.

## In-process features and the separate daemon

Full declares Torch **2.15.0**, TorchVision **0.29.2** and Transformers **5.22.2**
for existing in-process DA2 vision and RAG/embedding consumers. Moving the HTTP
daemon to another interpreter does not move those application consumers. Full
also declares `onnxruntime-gpu` for existing voice and floor features, with
faster-whisper, Piper and audio dependencies. Its CPU API remains available
through that single GPU distribution. ONNX GenAI is not installed. CPU and GPU
ONNX distributions must not share a namespace.

The CUDA daemon has its own `multi-runtime-cuda` component environment and keeps
matching Torch/Transformers versions. `MULTI_RUNTIME_COMPONENT_PYTHON` selects
that interpreter; the documented default environment is
`.venv-components/multi-runtime`. It must not fall back to the application `.venv`
or a system-site-packages environment. Existing model/device/precision and HTTP
settings remain separate from dependency installation. Ollama remains an external
HTTP service; it does not require installing another Python inference engine into
the application. CUDA is an accelerator, not an engine: Ollama can use its own
GPU backend, while in-process vision/embeddings select their own device. The
`multi-runtime-cuda` name identifies the qualified GPU dependency target; daemon
execution still supports explicit `auto`, `cuda` and `cpu` settings. This GPU
package set is not a lightweight CPU-only installation profile. Systemd selection, service starts, model assets and device/CUDA
acceptance remain explicit operations, not effects of profile bootstrap.

## Standard Full CUDA voice

Both `full` and `full-ci` use `onnxruntime-gpu==1.31.1` by default.
They include `nvidia-curand==10.4.2.66` from CUDA Toolkit 13.2.2 and
`nvidia-cublas-cu12==12.9.3.13` for CTranslate2 4.8.5. The latter adds
`nvidia-cuda-nvrtc-cu12==12.9.86` transitively. Full has 213 locked packages;
Full CI adds the shared CI tools for a total of 259. The redundant
`full-ci-cuda` profile and its install artifacts are retired. The independent
legacy Rider checkout and its environment are outside this application profile.

[ONNX Runtime upstream](https://onnxruntime.ai/docs/get-started/with-python)
requires one runtime distribution per environment and documents that the GPU
package also provides CPU functionality. Piper 1.8.0, Faster Whisper 1.2.1 and
Magika 0.6.3 still name the CPU distribution in package metadata. The Full profiles
substitute the GPU provider for those three consumers only, checking its actual
version against each original specifier. All other active requirements, including
extras, must be satisfied without substitution.

The official [CTranslate2 4.8.5 Linux wheel build](https://github.com/OpenNMT/CTranslate2/blob/v4.8.5/python/tools/prepare_build_environment_linux.sh)
uses CUDA 12.8 and cuBLAS 12 with dynamic loading. Its
[loader](https://github.com/OpenNMT/CTranslate2/blob/v4.8.5/src/cuda/cublas_stub.cc)
requests `libcublas.so.12`, which Torch's cuBLAS 13 cannot supply. The parallel
[NVIDIA cuBLAS 12 wheel](https://pypi.org/project/nvidia-cublas-cu12/12.9.3.13/)
and [NVRTC 12 wheel](https://pypi.org/project/nvidia-cuda-nvrtc-cu12/12.9.86/)
provide that active compatibility runtime without replacing Torch's CUDA 13
libraries. Their directories are `nvidia/cublas/lib` and `nvidia/cuda_nvrtc/lib`;
CUDA 13 uses `nvidia/cu13/lib`. This is not an obsolete cache or a separate
application environment. Current upstream wheels do not offer a CUDA 13-only
CTranslate2 replacement.

As checked on 2026-11-09, the [NVIDIA archive](https://developer.nvidia.com/cuda-toolkit-archive/)
lists Toolkit 13.5.0 as latest and 13.4.3 as archived; the
[13.5.0 PyPI release](https://pypi.org/project/cuda-toolkit/13.5.0/) is dated
November 4. The [PyTorch 2.15 support matrix](https://github.com/pytorch/pytorch/blob/v2.15.0/RELEASE.md)
identifies CUDA 13.2 as stable and 13.4 as experimental. The selected Torch wheel
requires Toolkit **13.2.2** and cuDNN **9.26.0.51** exactly. Keep those pins:
installing the newest toolkit globally does not replace a wheel's required
runtime or CTranslate2's SONAME 12. The NVIDIA driver is a separate layer and
supports older CUDA applications through [backward compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html).

Use the profile bootstrap for a fresh installation:

```bash
source .venv/bin/activate
python scripts/bootstrap_dependency_profile.py --profile full-ci --venv /explicit/path/to/full-ci
```

Do not run plain `pip install -r requirements-full.txt` or
`requirements-full-ci.txt`; upstream metadata would add the conflicting CPU
wheel. Bootstrap installs the complete hash lock with `--no-deps`, then verifies
the exact inventory and every active dependency. It preserves the raw nonzero
`pip check` result and its three missing-CPU-distribution messages. Only the
documented Piper/Faster Whisper/Magika mismatches are accepted by the provider
check. Any additional pip error, missing dependency, incompatible version or
second ORT distribution fails verification. Other profiles retain the standard
clean-`pip check` requirement.

The one supported migration accepts the exact retired `full-ci-cuda` release:

```bash
python scripts/bootstrap_dependency_profile.py --profile full-ci --venv /existing/owned/gpu-venv --update
```

Before any package mutation, bootstrap checks the old ownership receipt's lock
hash and all 258 original package versions; only its optional pinned wheel
bootstrap tool may be present in addition. The update advances cuBLAS and adds
NVRTC, verifies the complete canonical Full CI graph, then writes the new owner.
An unknown owner, modified inventory, CPU ORT or a failed final verification
cannot receive the new ownership receipt. Existing CPU Full environments need a
fresh GPU environment; no in-place mixed-ORT installation is permitted.

The launcher must expose libraries from its own environment before Python starts:
`nvidia/cu13/lib`, `nvidia/cudnn/lib`, `nvidia/cublas/lib` and
`nvidia/cuda_nvrtc/lib`. The project GPU launcher discovers these directories.
Bootstrap does not alter service configuration or load models. Voice acceptance
is a separate operator check outside code gates and pre-push.

The two replacement locks retain the frozen release graph, refresh only the
declared CUDA changes from official PyPI artifacts, and validate the full
dependency metadata. Their receipts explicitly record
`METADATA_VALIDATED_WITH_ONNX_PROVIDER_SUBSTITUTION`, source lock identities
and artifact hashes; this is not an installation or model qualification.
The other five lock graphs remain unchanged.

## Removed declarations and retained scope

The Light usage audit removed direct `aiortc`, `av`, `tiktoken`, `anthropic` and
`werkzeug` declarations without a confirmed application consumer in the reviewed
scope. This is a reduction of direct policy inputs, not a ban on valid transitives:
for example, Full voice may still require AV through faster-whisper. NumPy remains
a real core/daemon/Rider dependency; the candidate uses **2.5.4** for Python 3.14.

Rich belongs to CI tooling. Packaging is explicit in CI/build, and bootstrap
installs the pinned build toolchain before invoking the generator and lock audit.
`google-genai` remains because Google provider activation checks SDK availability.
Web DDGS/Tavily clients have dynamic consumers and remain Full features.

Legacy SK/AutoGen/FLAML, GraphRAG SDK, Optimum, WebRTC VAD and Locust are not part
of the new Full runtime. Existing consumer behavior determines feature groups;
adding every historical experiment back to Full is not the profile contract.

ONNX LLM/GenAI, standalone legacy ONNX extras, vLLM and Academy remain
explicitly deferred. GPU ONNX for application voice is standard in Full and Full CI; it does not
activate the deferred ONNX LLM/GenAI installers. The Full voice/floor group
remains independent of those profiles. A later ONNX LLM component needs a concrete model
consumer and its own qualification. vLLM remains outside this candidate; model training uses its isolated component.
Legacy overlay bytes may still include a changed shared Light input; byte identity
does not freeze their effective graph or establish compatibility.

## Generation, bootstrap and evidence

Activate the repository virtualenv before Python tooling. The metadata checks are:

```bash
source .venv/bin/activate
python scripts/dev/dependency_profiles.py generate --check
python scripts/dev/dependency_profiles.py audit-locks
```

Generation and resolution must produce matching Python 3.14 inputs, lock files and
receipts before installation. A lock-integrity result such as `RESOLVED_ONLY` is
not an installation, model-runtime or security result. No such qualification is
inferred from resolution alone. The local results below state what was actually
installed and tested. A successful Full
CI installation does not prove an exact Full installation or unchanged Full
closure; reports must name the profile, interpreter, inventory and actual checks.

The explicit interfaces, after matching artifacts exist, are:

```bash
python scripts/bootstrap_dependency_profile.py --profile full-ci --venv /explicit/path/to/full-ci
python scripts/bootstrap_dependency_profile.py --profile multi-runtime-cuda --venv "$PWD/.venv-components/multi-runtime"
```

Existing targets require explicit `--update`; bootstrap rejects incompatible
ownership, system site packages and mismatched inventories. The component cannot
replace the application `.venv`. Source, hash, artifact and storage checks remain
active. Desktop source distributions are restricted to exact versions in
`source_distributions`; every archive must match the official-source SHA-256 and
the selected lock receipt. Builds use the four pinned build tools with build
isolation disabled, so unpinned build backends are not fetched. Evdev additionally
requires a C compiler and Linux input headers. The default remains wheels-only.
Actual build results must be reported rather than presumed compatible. Parse
`.env` files as data (for example with python-dotenv); never execute an example
configuration with shell `source`.

Docker launchers continue to provide Light/API. They direct Full, Full CI and the
CUDA component to host bootstrap instead of advertising an unavailable Full image.
Installing a profile does not start services, load models or migrate the retained
operator installation. Preserve the old compatible checkout/environment for any
separately authorized rollout and rollback.

## Security evidence remains profile-specific

SCM projects and required security checks remain enabled. The `.snyk` file selects
Python 3.14 explicitly; hosted Snyk chooses its own patch within that minor line,
while local installation qualification requires exactly 3.14.8. Full installation ERROR,
previous advisory findings and the Snyk support investigation are not resolved by
renaming or reducing profiles. Fresh evidence must identify the exact graph and
scope; local CLI results do not override failed hosted checks.

`audit-security` requires an explicit active profile, exact interpreter, output
location and SCM organization. Generated inputs, active locks, inventory and
bootstrap tools are checked before querying dependencies. Failed preflight
invalidates an old PASS report. Partial, unavailable or inconsistent output remains
incomplete ERROR. Local receipts do not substitute for hosted security checks.

Sources: [Python 3.14.8](https://www.python.org/downloads/release/python-3148/), [Snyk SCM Python selection](https://docs.snyk.io/supported-languages/supported-languages-list/python/scm-integrations-and-python).

## Local candidate checks (2026-10-18)

Six Python 3.14.8 locks passed integrity/shared-version checks. Full CI and the
CUDA component were installed into separate isolated candidates and passed exact
inventory comparison plus `pip check`. Exact Full was resolved, not separately
installed; Full CI must not be reported as that installation.

One offline Gemma4 CUDA test used the existing local model: load 30.44 seconds,
one short response `OK.`, followed by unload/stop. VRAM returned from 11136 MiB
to the 1185 MiB baseline. No model matrix or new model download was performed.

Local Snyk covered Light (94/94), CI (151/151) and build (4/4) without findings.
Installed CUDA component and Full CI audits were complete but returned 16 and 17
advisory IDs respectively. The shared 16 affect Torch, Transformers and
Accelerate; Full CI also reports Bleach. Snyk supplied no `fixedIn` versions.
These are findings, not a green security gate; no additional ignore was added.
The retained reports name their commit, inventory and scan scope.

The final local PR-fast gate at `f31da758` passed: **5134 tests, 6 skipped**,
14 coverage floors, and mypy across **438 source files**. A separate helper run
passed 246 tests with 91.97% statement and 88.10% branch coverage; it does not
replace the production Sonar scope, which excludes scripts.

SonarScanner 8.1.0.6389 authenticated with the newly supplied local credential,
analyzed Python/TypeScript and uploaded coverage plus the report for `f31da758`.
The organization plan denied quality-gate access for a non-main branch. The gate
is therefore **unavailable, not PASS**. No main analysis or hosted settings were
overwritten. A PR analysis is a separate next step; another token rotation is not
required by this result.

Temporary Light smoke and Python-provisioning tool environments were removed
only after their receipts were retained. The two remaining candidate environments
occupy about 11.2 GiB together; the operator environment and existing model cache
were preserved. The test model was unloaded and its owned process stopped.

## Model stack migration (2026-11-09)

The shared model group now pins Torch 2.15.0, TorchVision 0.29.2 and
Transformers 5.22.2. The Linux locks select CUDA Toolkit 13.2.2 and Triton 3.9.0.
Full and Full CI use Sentence Transformers 6.2.0, SciPy 1.18.1 and GPU
ONNX Runtime 1.31.1. All Hub consumers in the managed profiles use Hub 2.4.0
and hf-xet 1.8.0, including CI; its separate httpx2, httpcore2 and truststore
dependencies are recorded in the locks. The application still uses httpx 0.28.1.

Pillow advances to 13.0.0 after the dependency audit reported fixes unavailable
in 12.3.0. The optional Rider host retains its separate previous environment.
PyAV stays at 19.0.1 because the audited 19.0.2 file-input path is incompatible
with Faster Whisper 1.2.1's metadata_errors argument. Venom's PCM flow has
separate acceptance evidence. PEFT, Accelerate, bitsandbytes, TRL and Datasets
retain their current declared versions. These are explicit version decisions,
not permission to relax the exclusive ONNX distribution rule.

### Optional Rider integration

The host module is an independent repository. Its current CUDA perception runs
inside its host process; installing a second venv alone does not move that code.
Preserve the existing Rider host checkout and its complete environment until a
companion change provides and qualifies a separate GPU process entry point.
The retained environment is not selected automatically. The current local
operator configuration still includes Rider in `API_OPTIONAL_MODULES`. Before
activating the new Full interpreter, use a dedicated configuration that omits
that manifest. If Rider remains in use, keep its previous complete Venom host
process/checkout/environment on separately assigned addresses and ports until
the companion GPU boundary is implemented. Do not copy the current optional
module configuration blindly into the new interpreter; do not modify the
physical Pi to resolve a host dependency conflict.

The optional GPU profile must declare ONNX Runtime GPU and its required cuRAND,
and demonstrate CUDA/DLPack without CPU fallback. It must never overlay CPU ORT
in the new Full environment or force the core application back to older Torch.

The device source checkout uses its own development interpreter (Python 3.12).
The physical Rider-Pi remains on manufacturer Debian 11 and Python 3.9. Its
deployment, Python upgrade and motion tests are separate operations. Core
acceptance uses fixture protocol/capability/telemetry exchanges and saved frames.

### Qualification and activation

Create fresh candidate environments with the documented bootstrap and verify
their exact inventories plus pip check independently, including exact Full.
Use the candidate Full CI interpreter for code gates through
`VENV=/absolute/candidate/path make pr-fast`. Code gates use doubles and do not
perform model inference, GPU allocations or physical device acceptance.

Gemma E4B and the active E2B profile select SDPA for text and eager attention
for audio. Unified Gemma 12B retains SDPA. New training environments require
new model-specific smoke receipts. Existing checkpoints must resume using their
original checkout, interpreter, lock and receipt; never rewrite historical
qualification identities to claim compatibility with this migration.

The authorized Hub 2.4.0 download of Gemma's config succeeded. That repository
reported `gated=false`, so this is an authenticated public read, not proof of
private/gated model access. This limitation remains recorded for rollout.
Prior overlay model runs are supporting evidence, not proof for freshly locked
environments. Gemma E4B/12B training still requires a suitable GPU; the 12 GB
host could not complete E4B preparation in the previous qualification.

Publishing the code does not switch active venv symlinks or restart services.
Retain the old checkout and complete environments for rollback. Activate each
candidate interpreter only as a separately requested deployment, then perform
the operator's Studio, Full voice and optional Rider acceptance flows.

The migration's dependency audit also requires aiohttp 3.14.5, GitPython 3.2.1,
filelock 4.2.10, pyasn1 >=0.6.5, pypdf 6.21.4, virtualenv 21.15.6 and the
setuptools 84.2.1 build toolchain. OAuthlib 4.0.1 is selected transitively.
Regenerate and qualify Light, CI and build as well as the model profiles when
these shared security constraints change. Keep previous audit results under
their original lock identity; do not waive findings through ignore entries.

### Historical training profile name

There is no active Granite model in the current operator scope. Gemma 4 and
FunctionGemma both reference the historically named
`granite-operator-training-linux-py314.txt` lock. Preserve that path and prior
checkpoint identities; it identifies shared training dependencies, not a
requirement to restore or qualify Granite weights.

`requirements-granite-operator-tests.txt` belongs only to automated code
contracts. Its CPU Torch wheel supports tiny tensor doubles for checkpoint,
optimizer and resume logic without GPU access or model downloads. It is not a
model-serving or training profile, and its tests do not qualify any model.
Actual Gemma/FunctionGemma training qualification uses GPU and remains separate
from CI, quality gates and Git hooks.
