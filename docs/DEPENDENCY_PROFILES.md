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
```

The resolver uses `pip install --dry-run --ignore-installed`, a private cache,
and official PyPI artifact hashes. Every application extension freezes its
parent lock; already-resolved application locks constrain overlapping packages.
A genuine resolver conflict is an error, not an invitation to install with
`--no-deps`. Components resolve independently with `--profile vllm`,
`--profile onnx-gpu` and `--profile academy`.

A lock receipt (`requirements/locks/*.json`) records the policy/lock hashes,
resolver/interpreter platform and the exact official URL/hash of every selected
artifact. It says **RESOLVED_ONLY**: dependency resolution is not a model test,
a security assessment, a successful install, or a complete product acceptance.
Missing locks do not authorize installing an unfrozen candidate as a release.

Install into a fresh environment without system-site-packages:

```bash
python3.12 -m venv /absolute/path/to/new-light
/absolute/path/to/new-light/bin/python -m pip install --require-hashes \
  -r requirements/locks/light-linux-py312.txt
python scripts/dev/dependency_profiles.py verify --profile light \
  --python /absolute/path/to/new-light/bin/python
```

Verification requires every locked version, `pip check` success and an isolated
venv. An executable/interpreter error is ERROR. Test two independent clean
installations and compare their full inventories. Keep raw output and hashes
outside tracked source; do not copy operator secrets or alter an old venv.

No dependency command starts/stops a model, controls hardware or changes an
operator endpoint. Runtime/model/SSE/tool/cancellation/storage tests, scanner
completeness and isolated lifecycle acceptance remain separate release gates.
Do not declare Full, GPU engines or Academy qualified based on a successful
Light/CI installation or mock-based contract tests.
