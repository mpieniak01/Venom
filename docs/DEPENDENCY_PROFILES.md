# Dependency profiles and component boundaries

`config/dependency-profiles.json` is the single editable dependency policy.
`python scripts/dev/dependency_profiles.py generate` creates the root installation
inputs and compatibility aliases. `generate --check` detects drift without editing.
Do not hand-edit generated requirements, constraints or platform locks.

## Product and execution are different axes

| Profile/component | Package owner | Execution contract |
| --- | --- | --- |
| Light | Application base | API/UI, MAF and HTTP clients; Ollama is a separate service. No Python inference engine, Torch or training packages. |
| Light + CI (`ci`) | Light plus test tools | Complete Light versions, including transitives, remain frozen. No models or GPU are required by the dependency checks. |
| Full | Light plus local features | RAG, vision, CPU ONNX and voice. Only the CPU `onnxruntime` distribution owns the `onnxruntime` namespace. |
| Full + CI (`full-ci`) | Full plus the same test tools | Full's complete package graph remains frozen. |
| vLLM | Separate server interpreter | OpenAI-compatible HTTP inference. Its CUDA/Torch, NumPy, MCP and FastAPI graph does not modify the application environment. |
| ONNX GPU | Separate worker interpreter | GPU ORT/GenAI only; no CPU ORT package. The inference bridge and actual model must pass separate runtime qualification. |
| Academy | Separate opt-in training environment/image | Training and merge/export/load artifacts. Its Torch/TRL versions do not silently replace application inference packages. |

`light`, `full`, `llm_off` and their existing runtime aliases remain runtime
settings, not additional dependency bases. In particular, `llm_off` does not start
Ollama merely because Light packages are installed. Full excludes Academy's
training-only packages; PEFT/Transformers/Torch used for inference are distinct
from training ownership.

The migration uses selected released packages: `agent-framework-core` and
`agent-framework-openai`, with `agent-framework-orchestrations` for workflows.
The `agent-framework` metapackage and `[all]` are deliberately absent. Application
OpenAI 2.x serves the current compatible provider/RAG contract; selecting the
latest major OpenAI or MCP independently is not qualification of that contract.

## Why the boundaries are necessary

MAF's all-extra currently requests MCP 1.x while vLLM 0.31 requires MCP 2.x.
vLLM also owns a different CUDA/Torch/OpenCV graph. It therefore runs behind the
existing inference HTTP boundary instead of being an application overlay.

Piper and faster-whisper require the **distribution** `onnxruntime`. GPU GenAI
requires `onnxruntime-gpu`; the two distribution records own overlapping import
paths. Installing both, suppressing dependencies or deleting a declaration is
not a supported solution. Full keeps voice/CPU ORT together; GPU ORT belongs to
its own interpreter. The generator rejects a lock with overlapping CPU/GPU ORT
or GenAI distributions, including transitive occurrences.

The Academy requirements file now describes the separate training component,
not an application overlay. `requirements-profile-onnx.txt` similarly describes
the GPU worker. Read their generated boundary comments before installation.
Legacy API/web/Docker requirement names point to Light. The legacy ONNX CPU and
voice-extra names point to Full; those aliases do not claim an independently
qualified CPU LLM product or a second version policy.

## Locks and reproducibility

The initial lock target is **Linux x86_64, CPython 3.12**. Other interpreters and
platforms need a separate qualification, not a copied lock filename. Resolve in
this order using a disposable tool interpreter:

```bash
python scripts/dev/dependency_profiles.py generate
python scripts/dev/dependency_profiles.py lock --profile light
python scripts/dev/dependency_profiles.py lock --profile ci
python scripts/dev/dependency_profiles.py lock --profile full
python scripts/dev/dependency_profiles.py lock --profile full-ci
python scripts/dev/dependency_profiles.py audit-locks
```

The resolver uses `pip install --dry-run --ignore-installed --no-cache-dir`
and official PyPI artifact hashes. Every application extension freezes its
parent lock; already-resolved application locks constrain overlapping packages.
A genuine resolver conflict is an error, not an invitation to install with
`--no-deps`. Components resolve independently with `--profile vllm`,
`--profile onnx-gpu` and `--profile academy`.

Each effective profile has its own policy fingerprint. Updating an unrelated
training/engine component does not invalidate an unchanged Light graph. The
full policy hash records the context at resolution; the effective profile hash
is the current compatibility check.

A lock receipt (`requirements/locks/*.json`) records the policy/lock hashes,
resolver/interpreter platform and the exact official URL/hash of every selected
artifact. It says **RESOLVED_ONLY**: dependency resolution is not a model test,
a security assessment, a successful install, or a complete product acceptance.
Missing locks do not authorize installing an unfrozen candidate as a release.

Install into a fresh environment without system-site-packages:

```bash
python3.12 scripts/bootstrap_dependency_profile.py --profile light \
  --venv /absolute/path/to/new-light
python scripts/dev/dependency_profiles.py verify --profile light \
  --python /absolute/path/to/new-light/bin/python
```

Verification requires every locked version, `pip check` success and an isolated
venv. Installed bootstrap-only additions must match the build policy too; a
vulnerable venv seed `pip` cannot pass by appearing on a package-name allowlist.
An executable/interpreter error is ERROR. Test two independent clean
installations and compare their full inventories. Keep raw output and hashes
outside tracked source; do not copy operator secrets or alter an old venv.

No dependency command starts/stops a model, controls hardware or changes an
operator endpoint. Runtime/model/SSE/tool/cancellation/storage tests, scanner
completeness and isolated lifecycle acceptance remain separate release gates.
Do not declare Full, GPU engines or Academy qualified based on a successful
Light/CI installation or mock-based contract tests.


## Source builds in Full

The initial Full graph contains source archives for optional GUI/VAD packages.
Their hashes lock the sources, not unspecified future build dependencies. The
technical `build` component pins pip, setuptools, wheel and packaging. Bootstrap
it only into a **fresh** target before resolving/installing Full; it is not a
runtime overlay to install after Full.

```bash
/absolute/path/to/new-full/bin/python -m pip install --require-hashes \
  -r requirements/locks/build-linux-py312.txt
SOURCE_DATE_EPOCH=946684800 PYTHONHASHSEED=0 \
  /absolute/path/to/new-full/bin/python -m pip install --require-hashes \
  --build-constraint requirements-build-constraints.txt \
  -r requirements/locks/full-linux-py312.txt
python scripts/dev/dependency_profiles.py verify --profile full \
  --python /absolute/path/to/new-full/bin/python
```

Record the built wheel's SHA256 and source origin hash as well as the build
constraint hash. Cached immutable built artifacts can be shared between clean
installations; inventories and exact artifacts must still be compared. Source
build success is not evidence for STT/TTS or model output. Test the CI extension
by installing `full-ci`'s lock into each independently built Full environment and
verify that every Full package remains at the same version. Keep both the Full
and Full+CI phase receipts.

`audit-locks` validates complete lock receipts and common application versions.
It reports `LOCK_INTEGRITY_ONLY`, not product acceptance. It also checks that a
resolver report has not silently omitted a requested direct dependency.


## Bootstrap, CI and Docker entry points

Use the standard-library bootstrap from the repository root, with an explicit
new target and a Python 3.12 interpreter on Linux x86_64:

```bash
python3.12 scripts/bootstrap_dependency_profile.py --profile light \
  --venv /absolute/path/to/new-application
python3.12 scripts/bootstrap_dependency_profile.py --profile ci \
  --venv /absolute/path/to/new-application --update
python3.12 scripts/bootstrap_dependency_profile.py --profile vllm \
  --venv /absolute/path/to/new-vllm-component
```

The bootstrap validates lock ownership and hashes, creates an isolated venv,
installs the declared build toolchain in a fresh target, audits generated inputs
and all locks, installs with artifact hashes and runs `pip check` plus inventory
verification. Full and Full+CI additionally use the generated build constraints.
It writes `.venom-dependency-profile.json` only after successful verification.
There are no service starts or runtime configuration changes in this procedure.

Installers and the resolver disable pip caches. Bootstrap checks free space
before venv creation and every pip mutation. With WSL on a dynamically allocated
VHDX, also pass `--storage-root /mnt/f` (use the actual hosting volume), since guest
ext4 free space does not measure Windows capacity. `--min-free-gib` may increase
profile floors, never lower them. Run disposable qualification installs one at a
time, save their receipts, then remove the owned environments. Keep models and
operator environments separate from disposable data.

An existing target requires explicit `--update`. Additive transitions such as
Light to CI or Full to Full+CI retain their common locked versions. A target
with packages outside the selected profile and declared build toolchain is
rejected before installation: choose a fresh target to reduce a profile. The
bootstrap does not silently uninstall packages or repurpose an old SK/operator
venv. During `--update`, existing bootstrap-only tools are refreshed from their
hash-locked entries. Packages owned by the selected application/engine lock retain
that lock's versions; for example, vLLM's setuptools is not replaced with the build
component's setuptools. Engine/training components cannot use the application's
repository `.venv`. `verify` also rejects undeclared extra packages, so a populated
Full environment cannot be reported as a clean Light installation.

The Make CI bootstrap and dependency-installing GitHub workflows call this same
entry point. CI includes the pinned `pip-audit` and `flake8` tools; workflow steps
do not append independently resolved Python tools. `scripts/docker/venom.sh`
installs optional engines under `${VENOM_COMPONENTS_DIR:-.venv-components}` in
separate profile environments. Configure and qualify their executable/endpoint
before activation; installing a component does not prove its lifecycle works.

The backend Dockerfile installs the Light hash-lock directly in an isolated
`/opt/venom-venv`, using an immutable Python 3.12 amd64 base image digest. Its
build context excludes local venv/cache and credential files. A static payload
regression test verifies that every referenced requirements include is copied;
the old pair of requirements aliases omitted their dependent Light file.
A Docker build and runtime acceptance still require an isolated usable Docker
engine. Static checks and successful host installs are not a container smoke.

Initial local dependency qualification used two independent installations for
Light, CI, Full, vLLM, ONNX GPU and Academy, then extended both Full environments
to Full+CI. Every pair had identical complete inventories and successful
`pip check`; no model or service was activated by those installation checks.
The complete locked Full package graph must remain unchanged in Full+CI. The build policy
and the CI graph both pin `pip` 26.2.1. Earlier local receipts
with bootstrap pip 24.0/25.3 are historical: those tool versions fail the current
bootstrap check. Updating that tool is recorded separately from product package
invariance and does not qualify model behavior or security of other packages.
Raw local receipts belong under ignored `docs_dev/266/`, rather than pretending
`RESOLVED_ONLY` checked-in lock metadata is full runtime qualification.

## Compatibility decisions from real consumer probes (266)

Full uses Venom's own NetworkX/LanceDB RAG implementation. The standalone
`graphrag` and `litellm` SDKs have no runtime consumers and are removed from the
profile; this does not remove Venom graph storage, retrieval or MAF synthesis.
Qualification blocks both SDK imports while exercising actual local embeddings,
LanceDB retrieval and graph persistence. Its raw result remains separate from
lock integrity and installation results.

PyArrow is pinned to 25.0.1 while the shared application NumPy stays at 1.26.4.
A real RAG write exposed an import failure with PyArrow 26 despite `pip check`
passing: Arrow 26 requires NumPy 2 at runtime. This is a compatibility pin,
not a scanner exclusion. See [Arrow 26 release notes](https://arrow.apache.org/release/26.0.0.html)
and [Arrow 25.0.1 release notes](https://arrow.apache.org/release/25.0.1.html).
CI pins Ruff 0.14.8 to match the repository's pre-commit hook; newer Ruff defaults
are a separate lint-policy migration, not an implicit consequence of resolving CI.

Engine processes inherit only explicit OS/locale/device variables. Their PATH
starts with the selected component's interpreter directory and system tools;
application credentials, Python hooks and arbitrary VLLM/Torch flags do not cross
that boundary. Private cache and telemetry settings are constructed by the
controller. This preserves device selection without inheriting an operator venv.
