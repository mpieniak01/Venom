# Vast.ai: GPU environment operations

Shared backend service + terminal interface, independent of Venom frontend,
production inference routing and Rider control. Nothing starts at application
boot. Uses existing dependencies; no SDK or global package installation.

## Configuration

Store VAST_API_KEY in the existing .env.dev (SecretStr). From another checkout,
pass --env-file /absolute/path/to/.env.dev. Never copy the key to a rented machine,
startup script, report, argument or another secret store.

Reuse secrets/ssh/vast/connection.json with identity_file and known_hosts pointing
to existing absolute paths. Its public fingerprint must be registered in Vast.
The --ssh-profile override accepts only JSON files inside this checkout's
secrets/ssh directory (absolute or repository-relative paths). Traversal and
symlinks escaping that directory are rejected before reading. Key and known-hosts
paths inside the profile can still reference the existing shared absolute paths;
no key duplication is needed.
No account keys are created/deleted. Recommended scopes: misc, user_read,
instance_read, instance_write, billing_read; verify permissions per endpoint.

Plans, records and exports live in ignored .venom_runtime/vast, with private
atomic files and a per-plan process lock. Keep them after deletion for billing.
CLI calls the shared Environments service; future adapters must reuse it.

Copy config/cloud/vast/inspect.example.json or ollama.example.json into an ignored
local directory. Replace the image placeholder with a verified immutable digest
compatible with cpu_arch. Model-bound Ollama profiles also require an exact model name and digest.
An engine-only Ollama profile may leave both empty only with download_gb=0;
its ready operation checks version/tags without generation. Benchmark still
requires a model and digest.
Examples intentionally cannot rent until edited. No engine image is declared a
stable default after the observed CUDA errors. Template hashes are not digests.

- disk_gb: native provider field labeled GB, default 150; the identical value
  goes into search allocated_storage and creation disk. Historical GB/GiB
  ambiguity is not hidden by conversion: inspect actual bytes after allocation.
  Container disk cannot be resized in place.
- min_free_disk_bytes: measured free space required after allocation.
- RAM requirements use native MB fields. CPU and GPU memory are not added;
  GB10 shares physical memory.
- download_gb / upload_gb: explicit decimal-GB transfer budgets.
- duration_minutes: planned rental time including provisioning and downloads.
- Host bandwidth, OS and CUDA declarations are not facts about the container.
- Country codes filter search; unclear response location stays unknown.

Inspect startup only writes a completion marker. Ollama reuses the image tools
and an answering service, starting its own process only when absent. No Docker
inside Docker, drivers, Nginx or Venom installation. Own files are isolated under
/workspace/venom-vast. Existing supervisor/portal configuration is untouched.
Startup is versioned, hashed and locked.

A positive download budget explicitly permits ollama pull at startup/provision;
zero forbids downloads. Free space is checked first. Transfer budgets are estimates,
not enforced traffic caps. Gated/private models are outside this bootstrap profile.

## Host location, link and ranking

Poland is preferred by default (preferred_countries: ["PL"]), with other countries
as fallback. This is a preference, not a hard restriction. countries: ["PL"] or
--country PL restricts the search to Poland. Country codes are normalized.
Preferred countries are queried separately so that a global top 100 does not hide
Polish offers. Queries remain bounded: one global plus at most eight country
queries; rankings describe those candidates, not an exhaustive marketplace scan.

All sort modes put eligible offers first, then preferred countries in their
configured order. Within each group:

- balanced: reliability descending, weakest link direction descending, total cost ascending;
- price: quoted experiment total ascending, reliability, then link;
- network: min(download, upload) descending, reliability, then cost;
- reliability: provider reliability descending, cost, then link.

Use --no-country-preference for a global ranking without the Poland-first group.
Unknown metrics stay unknown and sort after known metrics for that criterion.
Invalid/missing required metrics cannot make an offer eligible. Rank alone never
rents a host and never changes the offer of an existing plan.

Recommended example profiles require at least 500 Mbps download, 200 Mbps upload
and 0.99 reliability, plus verified status. Change these explicit minima if needed.
Reliability is the provider's availability indicator, not customer reviews.
The API contract does not expose a customer-review count or star rating; reports
say user_reviews=not_provided. Verification also does not prove real application
performance, low latency or an uncongested route from the operator.

Network values are Mbps, matching Net Mbps in the maintained official CLI.
The endpoint reference currently labels inet_up/inet_down MB/s inconsistently;
raw fields are preserved and no implicit factor-of-eight conversion is applied.
Disk bandwidth remains MB/s. Country proximity is a preference, not measured RTT.
Host signals in each assessment show country, both link directions and reliability
in percent, alongside provider-declared provenance.

    python scripts/cloud/vast/vast.py --json offers --profile .venom_runtime/inspect.json --sort price
    python scripts/cloud/vast/vast.py --json offers --profile .venom_runtime/inspect.json --sort network --country PL
    python scripts/cloud/vast/vast.py --json offers --profile .venom_runtime/inspect.json --sort reliability --min-reliability 0.99
    python scripts/cloud/vast/vast.py --json offers --profile .venom_runtime/inspect.json --sort price --no-country-preference
    python scripts/cloud/vast/vast.py --json plan --profile .venom_runtime/inspect.json --offer OFFER_ID --min-download-mbps 500 --min-upload-mbps 200 --max-hourly 0.50 --max-total 1.00

The same overrides apply to offers, assess and plan. A plan stores its effective
profile, so create rechecks the exact saved minima and hard country restrictions.
Changing a search never silently changes a saved plan.

## Terminal flow

From repository root:

    source .venv/bin/activate
    python scripts/cloud/vast/vast.py --json account
    python scripts/cloud/vast/vast.py --json list
    python scripts/cloud/vast/vast.py --json volumes
    python scripts/cloud/vast/vast.py --json offers --profile .venom_runtime/inspect.json
    python scripts/cloud/vast/vast.py --json assess --profile .venom_runtime/inspect.json --offer OFFER_ID
    python scripts/cloud/vast/vast.py --json plan --profile .venom_runtime/inspect.json --offer OFFER_ID --max-hourly 0.50 --max-total 1.00 --finish destroy

Offers, assess and plan do not rent. Assessment is eligible/ineligible/unknown,
with missing fields and reasons. Performance remains unknown before measurement.

Inspect the returned plan_id. Plan records the exact offer/host/machine, profile,
image/model digests, startup hash, SSH reference, budgets and finish policy.
Plans expire after ten minutes.

**Create starts a paid rental.** This is the single explicit approval of the plan;
it never silently changes offers or starts a second resource.

    python scripts/cloud/vast/vast.py --json create --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json wait --plan PLAN_ID --timeout 120
    python scripts/cloud/vast/vast.py --json inspect --plan PLAN_ID --accept-new-host-key
    python scripts/cloud/vast/vast.py --json status --plan PLAN_ID

Create rechecks capacity, price, budget, registered SSH key and startup hash.
Price increases require a new plan. Mutations are never automatically retried.
Timeout/malformed creation response leaves outcome_unknown: run reconcile,
including later if visibility is delayed. Empty listings do not justify another
rental. A lost observation does not mean a resource was stopped or destroyed.

First SSH trust is explicit through --accept-new-host-key (OpenSSH TOFU).
Compare the fingerprint independently when possible. Later calls use strict
known hosts; changed keys fail. Agent forwarding and shared config are disabled.
SSH coordinates come from the API; model ports are not exposed publicly.

For an Ollama profile:

    python scripts/cloud/vast/vast.py --json provision --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json ready --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json benchmark --plan PLAN_ID > .venom_runtime/run-a.json
    python scripts/cloud/vast/vast.py --json compare .venom_runtime/run-a.json .venom_runtime/run-b.json

Provision explicitly repeats the same startup, including approved downloads.
Ready/benchmark never pull, install or restart managed services. Temporary private
SSH tunnels close on success/failure. Readiness checks installed digest and actual
generation. The bounded suite covers natural first load, three short cases, two
medium, two long, two concurrent requests and optional JSON, a synthetic image and a fictitious
tool that is never executed. Optional cases run only when listed in runtime.capabilities. Reports preserve context, engine/model versions,
prompt hashes, TTFT, prefill/decode and errors. OS/prefix cache may already be warm.
A CUDA error rejects this stack, not the GPU hardware. Incomplete runs are inconclusive.
Different suites/engines/models/settings are explicitly marked non-comparable.

## Costs and cleanup

    python scripts/cloud/vast/vast.py --json costs --plan PLAN_ID --from-utc 2026-10-16T00:00:00+00:00 --to-utc 2026-10-17T00:00:00+00:00
    python scripts/cloud/vast/vast.py --json export --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json stop --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json start --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json destroy --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json reconcile --plan PLAN_ID

Amounts use Decimal and separate:

1. Quote: search totalHour/dph_total for selected disk, plus explicit USD/TB
   transfer rates. Never add disk twice. Ambiguous legacy rates stay unknown.
2. Estimate: continuous quoted exposure since submission, not measured usage;
   may overestimate stopped time and does not prove a final bill.
3. Provider reported: paginated charges, UTC window, source=instance-ID.
   Sum parent amounts once, not parent plus nested items.

Invoices describe payments, not resource charges. Account credit and balance
are distinct fields. Credit changes cannot attribute one experiment's costs.
If Vast reports that host accounts cannot retrieve instance charges, or denies
billing access, the report is unavailable while quote/estimate remain available.
This is not a zero bill. Missing charges are pending. Present charges are provisional: provider
finalization timing is unknown.

Stop retains billable storage. Destroy requires a saved export and a subsequent
read to confirm removal; journal remains. Volumes is read-only inventory.
Cleanup never deletes unrelated instances, shared volumes or SSH keys.

    python scripts/cloud/vast/vast.py --json cleanup --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json monitor --plan PLAN_ID --timeout 600

Cleanup exports and uses the selected stop/destroy policy. Manual needs an
explicit operator action. Monitor is a bounded foreground process: on planned
duration expiry, it executes that policy. It is not a server-side TTL or hard
billing cap. WSL exit, network failure or early monitor exit may leave a paid
resource running. Confirm cleanup in the provider console. No daemon is installed.

## Validation

Tests use HTTP/SSH fixtures and never rent: ambiguous creation, price drift,
v0/v1 pagination, 403/410/429, stopped storage, delayed deletion, startup/backend
errors and partial billing. Live creation/SSH/bootstrap/deletion needs a separately
approved paid acceptance run. Read success does not verify write permissions.

Fixed REST origin: https://console.vast.ai. Redirects never forward Authorization.
Exports use allowlists: private SSH fields, instance tokens and environment are
excluded. JSON output has ok/result or ok/error; summaries support PL/EN/DE.
Local reports may include private host coordinates; sanitize before publication.

## Primary references

- [Authentication](https://docs.vast.ai/api-reference/authentication)
- [Offers and native units](https://docs.vast.ai/api-reference/search/search-offers)
- [Create/startup](https://docs.vast.ai/api-reference/instances/create-instance)
- [Instance pagination](https://docs.vast.ai/api-reference/instances/show-instances)
- [Charges](https://docs.vast.ai/api-reference/billing/show-charges)
- [Volume inventory](https://docs.vast.ai/api-reference/volumes/list-volumes)
- [Billing](https://docs.vast.ai/guides/reference/billing)

- [Official CLI network labels](https://github.com/vast-ai/vast-cli/blob/master/vast.py)
- [Provider verification](https://docs.vast.ai/host/verification-stages)



## Runtime recipes and installation templates

Scope of this increment: inspect/select public or account templates; prepare a
local immutable profile and its startup script; deploy using the existing
budgeted plan/create flow. No frontend, production routing, or paid benchmark is
enabled automatically.

| Recipe | Remote workload | Image prerequisites | Acceptance |
| --- | --- | --- | --- |
| inspect | Hardware and environment inventory | Python 3, SSH, GPU tools | SSH/capacity report |
| ollama | Text, vision and tool-capable models supported by Ollama | Ollama and curl | Generation; shared text suite + required capabilities |
| vllm | OpenAI-compatible model serving | vLLM, compatible CUDA/PyTorch, curl | Generation and shared benchmark over SSH |
| pytorch | Environment for Depth Anything/YOLO and Whisper | Compatible GPU PyTorch; selected task packages | Imports, CUDA availability and worker inventory |

PyTorch prepares a worker environment, not an inference API. The vLLM readiness
check is distinct from the shared performance benchmark for Ollama and vLLM.
A model supporting an API feature must still pass its workload test.

### Commands

Run from the repository root with the existing virtualenv activated.
The following commands inspect or prepare configuration; they do not rent:

    python scripts/cloud/vast/vast.py --json recipes
    python scripts/cloud/vast/vast.py --json templates --recommended
    python scripts/cloud/vast/vast.py --json templates --hash TEMPLATE_HASH
    python scripts/cloud/vast/vast.py --json resolve-image --image vastai/ollama:TAG --arch arm64
    python scripts/cloud/vast/vast.py --json prepare --recipe ollama --image vastai/ollama:TAG --arch arm64 --model MODEL --model-digest DIGEST --disk-gb 150 --download-gb 25 --template-hash TEMPLATE_HASH --output .venom_runtime/vast/ollama.json

Replace TAG, MODEL, DIGEST and TEMPLATE_HASH with inspected values. Public Docker
Hub and nvcr.io/nvidia tags passed to prepare are resolved to a verified Linux architecture manifest
digest before saving. The dedicated resolve-image command works without a Vast
key. Other registries can be supplied as an already pinned image in the profile;
their authentication and resolution are outside this increment. NVCR uses anonymous
pull tokens scoped to the selected public NVIDIA repository. No Vast key is sent.

prepare also accepts --profile for existing requirements and overrides for image,
architecture, model/digest, disk and download allowance. It creates a new file
with mode 0600 and refuses to overwrite operator configuration. Its JSON result
includes the exact startup script, selected recipe and profile. Use this profile
with offers, assess and plan, followed by explicit create, inspect, provision,
ready, qualify and benchmark. Creating a plan alone has no paid side effect.

For vLLM, --model is the Hugging Face repository and --model-digest must be its
40-character commit revision. The script pins model/code revision, binds port
8000 to loopback and does not enable trust-remote-code. GPU utilization (default
0.85), concurrent sequences (4), and context are profile settings. /v1/models
does not attest weight bytes: readiness reports the configured revision with that
limitation. For Ollama, the digest is verified against /api/tags instead.
Zero download allowance makes vLLM use offline Hugging Face cache.

For PyTorch, --worker-task vision selects Pillow/Ultralytics and --worker-task
audio selects faster-whisper; torch and transformers are always checked. Both
tasks are selected by default. If these are missing from the image, explicitly
supply --install-package NAME==VERSION and a positive --download-gb allowance.
Allowed packages are ultralytics, transformers, faster-whisper and pillow.
The generated script creates /workspace/venom-vast/worker-venv with access to the
selected image interpreter packages through a fixed .pth file (including when\nthe image uses /venv/main), pins installed torch/torchvision/torchaudio/numpy as pip
constraints, and installs wheels into that venv. Missing compatible wheels or a
dependency conflict fails provisioning instead of silently replacing the GPU
stack. Root package versions are pinned; transitive dependencies are resolved at
installation time, so use a prepared image/lock for fully reproducible workers.
No model weights, dataset or full Venom installation are included in that recipe.

### Template policy

Vast templates can contain environment variables, credentials, port mappings,
startup scripts and default commands. Listings export allowlisted metadata and
only presence flags plus a configuration fingerprint for executable fields.
Template hash identifies a template, not an image digest.

Preparation imports image identity/provenance and checks the SSH capability and
recommended disk size. The selected image repository must match the template.
Safe CPU/GPU/CUDA/driver/capacity constraints from extra_filters are preserved in
runtime.template_constraints. Known contradictions reject the offer; unresolved
rules remain explicit unknowns. Review CPU/GPU/CUDA/model requirements in the profile. Environment, port mappings,
args and startup are replaced by the reviewed recipe. The native template_hash_id
is intentionally not submitted to create: Vast merges inherited environment
values, which would make an empty override insufficient to remove hidden ports
or bootstrap commands. Profiles pin provenance; plan/create fetch the template
again and reject a changed configuration. This also means web template features
such as Jupyter, serverless launch scripts and automatic image-tag selection are
not activated by this workflow.

A compatible image architecture is necessary but does not prove a working GPU
runtime on a particular host. Inspect and readiness must verify it after rental.
In particular do not add shared CPU and GPU memory on GB10 to estimate capacity.
Provider recommended disk sizes are template minima, not model-cache estimates;
choose storage for image, weights, cache, temporary downloads and free reserve.
The existing download_gb is an estimated budget, not a hard network quota.

### Performance selection

offers/assess/plan accept --sort performance (DLPerf) or --sort value (DLPerf per
quoted USD/hour including disk), --min-dlperf and --min-gpu-mem-bw-gb-s.
Existing country preferences still take precedence; use --no-country-preference
for a global comparison. Metadata includes total_flops (TFLOPS), memory bandwidth
(GB/s), CPU/GPU characteristics, declared CUDA/driver and PCIe capabilities.
DLPerf is a provider benchmark, not measured LLM tokens/s. The API provides no
universal MIPS number and CPU GHz is not converted into MIPS.

    python scripts/cloud/vast/vast.py --json host-results --machine MACHINE_ID

Historical provider scores retain unknown units, model and test identifiers.
Empty history is not a zero score. A historical record without a score is not
performance evidence. Shared suite v4 additionally counts actual Unicode code
points and reports characters_s over complete request wall time, including load,
prefill and transport. This differs from backend decode_tokens_s and is never
estimated by multiplying tokens by a fixed constant.

### Read-only acceptance and limits

On 2026-10-16 the authenticated API returned 37 recommended SSH-capable templates.
Public Docker manifests resolved for Ollama ARM64, vLLM ARM64 and PyTorch AMD64.
No instance was rented or package installed on a remote host during this check.
Paid runtime/driver compatibility, model loading and billing settlement require
a separately budgeted acceptance. Local raw evidence remains in ignored
test-results/vast-recipes-live-readonly.json.

Primary references:
- [Template API](https://docs.vast.ai/api-reference/search/search-templates)
- [Template inheritance and overrides](https://docs.vast.ai/api-reference/creating-and-using-templates-with-api)
- [Provider benchmark API](https://docs.vast.ai/api-reference/search/search-benchmarks)
- [vLLM Docker deployment](https://docs.vllm.ai/en/latest/deployment/docker/)
- [Docker Registry API](https://docs.docker.com/reference/api/registry/latest/)


### Local file boundary

The Vast command entry point is an operator CLI, not an HTTP route or a registered
LLM tool. Its input profile, SSH profile, output path and report paths are explicit
local operator choices. Profile creation is exclusive and mode 0600 from the
first write; existing files are never overwritten. No file contents are returned
as a generic file-reading capability. A future HTTP/agent adapter must select
server-owned profiles and artifact destinations rather than forwarding arbitrary
client-supplied CLI arguments.

Benchmark suite v4 derives repeatable synthetic prompts from SHAKE-256 rather
than a general-purpose random generator. Old suite versions remain separate in
comparison reports; a prompt-suite change does not establish new host performance.


## Runtime qualification and remembered suitability

Selection, runtime readiness and workload suitability are separate observations.
A missing CUDA declaration is a candidate for diagnosis, not a rejection. Known
contradictory declarations reject selection; a matching declaration does not
prove actual GPU execution. Version comparisons use numeric components
(12.10 is newer than 12.9), never floating point. Driver version predicates are
enforced locally: the official Vast CLI documents reliable equality only, so a
server-side string range must not silently remove a compatible driver.

A profile has one runtime contract, saved into a checksummed schema-2 plan:

    "runtime": {
      "acceleration": "cuda",
      "min_cuda": "",
      "min_driver": "",
      "min_engine_version": "",
      "compute_capabilities": [],
      "capabilities": ["json"],
      "allow_cpu_offload": false,
      "max_ttft_s": null,
      "min_characters_s": null
    }

Set only requirements that the workload actually needs. Compute capabilities are
an exact allowlist (1210 means sm_121), not an ordered proxy for architecture
compatibility. prepare --capability json/vision/tools declares optional acceptance
cases; absent capabilities are reported as skipped rather than failed. CUDA and
driver declarations from OCI config are allowlisted and tied to the verified
config/image digest. Complex NVIDIA_REQUIRE_CUDA alternatives remain unverified;
they are not reduced to a guessed global minimum. Automatic image tags require
an explicit concrete tag before resolution. No registry layers are downloaded.

    python scripts/cloud/vast/vast.py --json qualify --plan PLAN_ID
    python scripts/cloud/vast/vast.py --json qualifications
    python scripts/cloud/vast/vast.py --json report --plan PLAN_ID

qualify warms the already installed model where applicable, then runs a bounded
CUDA driver kernel with readback and a small real PyTorch CUDA matrix operation
for PyTorch/vLLM. It records driver, exact compute capability, interpreter and
package versions. Existing image environments (including /venv/main and the
isolated worker venv) are discovered by the same helper used at startup.
No package installation, model pull, driver repair or service restart occurs.

Ollama qualification combines the loaded model digest from /api/ps with the
processor split reported by ollama ps. Unknown split stays inconclusive; partial
CPU offload fails unless explicitly allowed. Unsupported diagnostic PTX/JIT
results stay inconclusive rather than condemning the template. A successful
tiny probe does not prove all kernels or production workload stability.

ready reports API/model generation separately from qualification. benchmark
requires a suitable runtime observation before running the shared text suite.
It records synthetic request hashes, real Unicode characters per complete request
wall time, TTFT and provider token counts. Ollama-specific decode/prefill timing
is reported only when supplied; vLLM SSE usage does not invent decode duration.
Full workload suitability additionally evaluates required capabilities and
explicit TTFT/character-rate thresholds. Interrupted/partial evidence stays
inconclusive. The same suite version is used for both engine adapters.

The private journal retains scoped qualification evidence and an atomic index.
Known unsuitable exact image/configuration/workload/GPU/driver combinations are
excluded from offers/assess/plan/create by default. --retest on offers/assess/plan
is an explicit override of previous negative history, not of budget or known
compatibility checks. A new image digest, requirements or driver needs a new
qualification. Partial context is a hint and never a template-wide ban.
A transport error cannot overwrite a decisive prior observation. API readiness and runtime-only evidence cannot clear a failed workload. A
successful benchmark for the same host/configuration can supersede it. The
operation report is saved before updating the index; index failures are reported
separately without discarding the measured result. Report/index files remain after destruction.

report and qualifications are local-only and need no cloud credential. report
combines saved requirements, declarations, observations, suite and budget with
the last explicitly requested costs report. Missing final charges remain
pending/unavailable; no local report claims provider settlement or a hard cap.

### Acceptance boundary

All runtime tests in this increment use synthetic HTTP/SSH/driver fixtures.
Public registry metadata was inspected without renting a GPU. Actual image load,
kernels on rented hardware, engine offload and final billing require a separately
approved paid acceptance. PyTorch preparation/qualification does not yet expose a
remote vision/audio worker API, route Venom production requests or change the UI.

References:
- [NVIDIA NGC registry](https://docs.nvidia.com/ngc/latest/ngc-catalog-user-guide.html)
- [vLLM OpenAI-compatible serving](https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/)
- [Ollama loaded models](https://docs.ollama.com/api/ps)

## Managed Ollama in the existing chat

The chat selector offers **Ollama · Vast** only when a manually attached instance,
its SSH tunnel and Ollama API are available. An empty remote catalog cannot
provide a selectable model. Models are read from the attached server; local
models with the same name remain separate.

Run the existing CLI manually to search, plan, create, inspect and provision
the instance. Before creating it, prepare an Ollama profile with a pinned image
and model digest, explicit download budget, context and rental budget.
For trial-zero, use the Ollama recipe with a verified, pinned Ollama image,
empty model/model_digest and download_gb=0. This prepares the engine without
pulling weights. The inspect recipe remains available for inventory-only tasks.

With the Venom API running, use these commands (set --api-base if necessary):

    python scripts/cloud/vast/vast.py --json chat-attach --plan PLAN_ID --api-base http://127.0.0.1:8800
    python scripts/cloud/vast/vast.py --json chat-status --api-base http://127.0.0.1:8800
    python scripts/cloud/vast/vast.py --json chat-detach --api-base http://127.0.0.1:8800

The API owns the tunnel. Reloading the browser does not close it. Chat requests
continue through the existing Direct and Normal flows, using the selected
remote model and preserving runtime identity. A broken connection does not
switch the prompt to a local model. Detaching or cancelling generation does
not stop billing or destroy the rented instance.

After the trial, use the manual lifecycle commands to export and destroy the
trial instance. The cleanup-zero command confirms removal and reads the full
account instance list, including stopped instances. Success requires a count
of zero. Unknown state or a failed read is not zero; unrelated instances are
reported and never deleted automatically. trial-zero requires an engine-only
Ollama plan and runs create -> SSH/inspect -> provision -> ready -> export ->
destroy -> confirmed zero. Readiness checks GET /api/version and /api/tags
through SSH; an empty model list is valid for the engine-only trial. Provision
or API failure still triggers cleanup. This is not a model/GPU generation test.

    python scripts/cloud/vast/vast.py --json prepare --profile HOST_PROFILE.json --recipe ollama --download-gb 0 --output .venom_runtime/vast/ollama-zero.json
    python scripts/cloud/vast/vast.py --json trial-zero --plan PLAN_ID --timeout 120 --accept-new-host-key

HOST_PROFILE.json must already name a verified, pinned Ollama image for its
architecture and contain empty model/model_digest. Search, assess and plan with
the prepared profile, review costs, and explicitly invoke trial-zero. No inspect
or model-download plan is accepted for trial-zero. Chat uses a separate,
model-bound profile with a concrete model/digest; benchmark requires that model.

    python scripts/cloud/vast/vast.py --json cleanup-zero --plan PLAN_ID --api-base http://127.0.0.1:8800 --timeout 120
    python scripts/cloud/vast/vast.py --json verify-zero

Mock tests do not create paid resources. Real creation and chat generation
are separate, explicitly invoked operator actions.

Direct keeps up to 20 completed messages (50,000 characters) per remote target,
connection generation, model and session in the mounted chat. Reloading the
page clears this Direct context cache. Incomplete responses are not added to
context. The existing emergency STOP also aborts the active Direct HTTP stream.


### Host quality acceptance before Ollama model download

Ollama create now starts the engine only. Explicit provision inspects actual
container RAM/CPU/VRAM and disk, plus configured minimum driver/engine versions,
before downloading weights. Unknown or insufficient resources block provisioning;
manual lifecycle leaves the instance available for diagnosis.

Search sends capacity minimums to the provider and reassesses results locally.
Offer cpu_ram remains a declaration, not a guaranteed container limit.
Creation supplies context length and parallel requests through env; startup also
exports them, binds loopback and limits loaded models to one. Startup-v5 changes
the startup checksum: create a fresh plan rather than rewriting old plans.

Run create/wait/inspect/provision/ready and review GPU qualification before attach.
Engine availability is not GPU acceptance. Explicit chat request options may
override server context defaults; verify the effective context using ollama ps.
No undocumented memory-allocation flag or automatic replacement rental is added.


### Memory allocation semantics
Vast allocates baseline RAM/CPU proportionally to the machine GPU allocation:
https://docs.vast.ai/guides/instances/docker-environment
Offer cpu_ram is host RAM in MB; estimated baseline is cpu_ram*gpu_frac.
gpu_frac is the machine share, not shared ownership of one GPU. Allocated GPUs
are exclusive. cpu_cores_effective is already effective and is not scaled twice.
Default min_gpu_fraction is 0.001; an explicitly saved 1 retains its restriction.

Inspection separates host meminfo, cgroupv2 hard limit/current/high/swap/events,
cgroupv1 hard limit, and /dev/shm capacity. Swap/shared memory are not additional
RAM. A huge v1 sentinel means unlimited. Memory.high is soft pressure, and usage
includes reclaimable cache; limit-current is not model headroom.
Instance mem_limit/mem_usage/vmem_usage are retained as provider observations,
without guessing undocumented units. SSH hard limits remain the acceptance
source. A declaration and proportional estimate never replace actual checks.


## Multi-turn Direct acceptance

`python scripts/cloud/vast/chat_smoke.py` defaults to read-only preflight.
Explicit `--live --turns 2` (or 3) generates against an already selected target
and requires authorization for that execution. It never creates or deletes a host.

The smoke sends bounded history and requires exact recall of a random marker
on the second turn. A mismatch fails acceptance; the report contains only the
verification result, without conversation text or the marker. This does not
establish browser, Normal-mode, or general model-quality acceptance.

Preflight rejection before generation releases admission so the target can
be changed. Errors or cancellation after generation starts retain uncertainty;
never clear it automatically without evidence that the work has stopped.
