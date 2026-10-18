# Dependency profiles: Python 3.14 candidate

The canonical policy is `config/dependency-profiles.json`. This candidate targets
Linux x86_64, Python **3.14.8** (`platform.python` is the minor `3.14`;
`python_target` records the exact interpreter). Inputs and lock paths use `py314`.
These declarations do not establish installation, runtime or security qualification.
The existing Python 3.12 evidence does not qualify the new interpreter or graph.

## Six managed profiles

| Profile | Kind | Dependency boundary |
| --- | --- | --- |
| `light` | Application | MAF core, API, orchestration and the selected application clients; no local model engines. |
| `ci` | Application | Extends Light with the shared test, lint and audit tools. |
| `build` | Component | Pinned pip/setuptools/wheel/packaging toolchain used by explicit bootstrap; not a model environment. |
| `full` | Application | Extends Light with actual memory, vision, web/documents, desktop, hardware and CPU voice/floor consumers. |
| `full-ci` | Application | Extends Full with the same CI tools; its installed inventory is distinct from exact Full. |
| `multi-runtime-cuda` | Component | Independent minimal API/model/audio/OCR base for the CUDA daemon; does not extend Light. |

The five compatibility inputs `requirements.txt`, `requirements-runtime-common.txt`,
`requirements-docker-minimal.txt`, `requirements-profile-api.txt` and
`requirements-profile-web.txt` continue to represent Light. Generated SCM inputs
are self-contained and contain no recursive `-r` or `-c` directives.

## In-process features and the separate daemon

Full retains Torch **2.13.0**, TorchVision **0.28.0** and Transformers **5.17.0**
for existing in-process DA2 vision and RAG/embedding consumers. Moving the HTTP
daemon to another interpreter does not move those application consumers. Full
also declares CPU `onnxruntime` for the existing voice and Rider floor features,
with faster-whisper, Piper and audio dependencies. It does not install GPU ONNX
or ONNX GenAI. CPU and GPU ONNX distributions must not share a namespace.

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

ONNX LLM/GenAI, standalone legacy ONNX extras, GPU ONNX, vLLM and Academy remain
explicitly deferred. The active Full CPU voice/floor group does not activate those
legacy installer profiles. A later ONNX LLM component needs a concrete model
consumer and its own qualification. vLLM and training remain outside this candidate.
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
