# Venom runtime contract and MAF migration (266)

Status: implementation in progress. This document describes the migrated boundary;
it is not a release qualification or a declaration that all consumers are migrated.

## Ownership

`execution.agent_contracts` owns Venom conversation messages/history, mutable
completion settings and tool declarations. `execution.maf_runtime` uses the released
Microsoft Agent Framework Chat Completions provider. It contains no SK import or
fallback. `KernelBuilder` remains the public factory name so consumers need not
change their constructor contract. It now creates the small named service/tool
registry `AgentRuntime`; it does not emulate the complete Kernel SDK.

Existing agent methods keep their `process`, `process_with_params` and chat service
entry points. Aliases in migrated consumers are source migration aids. They are
Venom types, not instances of old SK classes. Extensions must import Venom contracts;
importing third-party SK types is not a supported compatibility promise.

## Model services and history

- Named service lookup remains available. `default` selects the first registered
  service if no explicitly named default exists; an unknown explicit name fails.
- Direct model completion does not construct a MAF agent or tool planner.
- A tool-enabled request uses MAF's native function loop. Native function call and
  result identities are kept in caller-owned history for the next model turn.
- Callers append the final assistant response. The runtime appends only intermediate
  tool messages; it does not execute a tool again while replaying history.
- Streaming emits existing text chunk lists. Cancellation and provider errors
  propagate; they are not converted to successful empty messages.
- The service owns and closes its AsyncOpenAI client, including internally created
  clients. The runtime closes its registered services on shutdown.
- Local provider token aliases are normalized to the existing Chat Completions
  `max_tokens` wire field using the SDK's public `extra_body` option. Nonstandard
  sampling options use that same public extension mechanism. Generation options
  cannot replace model routing, messages, tools or streaming configuration.

Gemini uses Google's official OpenAI-compatible Chat Completions endpoint. Optional
calendar and grounding capabilities remain separate skills. No paid API request is
required for offline contract tests.

## Tools and permissions

Use `tool_function` from `venom_core.execution.agent_contracts`. It preserves Python
method binding/signatures; the registry constructs native MAF FunctionTools from
bound callables. Generated MCP tools use this contract as well. The loader accepts
both the canonical decorator and its historical local alias `kernel_function`,
including asynchronous methods. Old generated files importing SK require migration.

Tools are filtered by plugin/function allow/exclude lists before being advertised.
Permissions are checked again at execution. A denial does not call the underlying
method. Existing action-specific enforcement inside skills remains in force.
Unknown function calls terminate rather than selecting another callable. MAF tool
limits are finite (5 rounds, 20 calls, 30 s best-effort budget); these SDK limits are
not a hard deadline for arbitrary blocking user code. Invocation is sequential and
exception details are not exposed to the model.

## Product routes retained

The cockpit still offers `direct`, `normal`, `complex` (see cockpit-chat-send and
execution_mode_planner). Direct uses the simple chat path, normal keeps orchestration,
and complex requests COMPLEX_PLANNING. Migration must not insert a planner/model
into direct or duplicate the shared template-response routing. End-to-end route and
performance qualification is a separate required gate; unit fixture transports do
not qualify a model or physical Rider-Pi.

## Validation boundary

`tests/test_maf_runtime.py` runs released MAF/OpenAI SDKs against deterministic HTTP
fixtures. Existing factory, agent, dispatcher, intent, history and skill tests are
migrated with each component. Clean Light/CI installation and lock integrity are
reported separately from actual inference, hardware and Docker qualification.

## Council turns and failure status

Council invokes one native deliberation turn per participant on the existing
Venom chat service. It does not call a standalone agent's `process()` workflow:
Architect's standalone method also executes its plan, which previously launched
subtasks before Council's coding/review stages. The Council role prompt now
actually reaches the model, and the request's generation parameters reach each
turn. The default turn budget is 512 tokens; explicit request values override it.
Standalone Swarm calls retain their existing `process()` behavior.

Only Guardian's final `TERMINATE` line completes the workflow. Missing approval,
provider failure or timeout raises `CouncilExecutionError`; the flow propagates
it to the orchestrator's failure handling. It no longer returns an error or
incomplete transcript as a successful task result. Success still returns the
existing transcript string; this is an intentional correction to error behavior.
The configured model selection also takes precedence over the legacy llama3
metadata default. These changes require a real API Complex test in addition to
deterministic native-workflow fixtures.

Every Coder candidate, including a revision requested by Guardian, goes through
Critic before Guardian. Only an exact first-line `APPROVED` from Critic advances;
`REPLAN` returns to Architect, other responses require Coder revision. Critic's
PolicyEngine checks the latest typed Coder message rather than a user-supplied
`CODE:` delimiter. Critical findings bypass the model, lesser findings stay in
its report. A provider failure never becomes implicit approval in Council.

Orchestrator and FlowCoordinator delegate Council execution to the existing
CouncilFlow. They retain configuration reuse and their broadcast entry points;
they do not maintain alternate error handling or silently substitute an endpoint.
Council uses consultation role prompts rather than standalone workflow prompts
(which required plan JSON/files even for a textual request). The same agents,
services, tool permission enforcement and generation options remain in use.

Review turns request a strict JSON Schema containing `decision` and `feedback`.
Both transport modes forward it through the native SDK; Venom additionally
validates the returned object. Invalid/truncated or unsupported responses fail,
rather than imply approval or trigger an indefinite formatting conversation.
Only explicit Guardian approval becomes the existing terminal `TERMINATE` line;
a rejection's feedback cannot inject that terminal line. Reviewers receive the
original task and current candidate/review rather than replaying old drafts and
critiques. The complete typed conversation remains available for auditing.


## Simple-route usage and receiver metrics

Simple chat keeps its direct route. Supported Ollama/vLLM/OpenAI-compatible
streams request `stream_options.include_usage`; this does not add inference.
The existing named `done` event optionally contains standard `usage` counters and
`usage_source: upstream`. Without reported counters it retains its empty payload.
The non-stream upstream response can carry the same metadata. Legacy native
Ollama counters normalize to their standard names without estimating a total.

The existing 202C collector uses those reported counts for end-to-end output
tokens/second. Receiver TPOT is `(E2E - first text latency)/(output tokens - 1)`;
it requires multiple nonempty text events and more than one reported output
token. It includes transport/batching effects and is not pure inference timing.
Single aggregated output has no observable inter-token interval. Missing usage
stays unavailable; inconsistent or malformed native usage fails a measurement.
Reports expose available/missing sample counts rather than filling missing data
with word counts, chunk counts or zeros.

Upstream references: [Ollama compatibility](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx)
and [Chat Completions streaming usage](https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events).
An interrupted stream may omit its final usage packet; that is not token evidence.


## Resource measurement in the existing 202C benchmark

`scripts/dev/202c_latency_memory_benchmark.py` accepts repeatable
`--baseline-root-pid` and `--candidate-root-pid`, `--resource-interval-sec`
(default 0.1 s, range 0.02–5 s), and `--gpu-index` (default 0). Supply known
API/engine process roots from the isolated qualification controller. It does not
infer roots from ports, names, or unrelated operator processes. Omitting roots
records `UNAVAILABLE` and starts no monitor. There are no new dependencies.

Each runtime has one resource window spanning measured repetitions, after its
first post-activation request and warmup. CPU is the sum of observed user/system
time deltas for those roots and their observed descendants; 100% means one logical
core. Birth-time identity checks reject PID reuse, and overlapping roots are
counted once. Sampled summed RSS may count shared pages more than once. Polling
can miss short-lived children, their final CPU time, and short memory spikes.

Node RAM (total minus available) and GPU device memory include unrelated
allocations. A single owned `nvidia-smi` monitor serves each window; its reader and
process have bounded cleanup, and target process trees are never terminated.
Actual sample counts/intervals, identities, errors, units, per-metric availability,
and scope are recorded in JSON. A missing read stays null; it never becomes zero.
Legacy summary memory keys alias these sampled node/device maxima. They are not
per-request memory estimates, isolated VRAM, or guaranteed inference peaks.

The first post-activation timing is not a proven cold unload/reboot cycle.
The script's existing percentage KPIs are exploratory and do not substitute for
266's frozen baseline-derived acceptance budgets, repeatable model artifacts,
all-route/lifecycle tests, or final release qualification. An unavailable latency
comparison cannot pass a KPI by substituting zero.


## Seed forwarding for reproducible Simple-route probes

The optional `SimpleChatRequest.seed` is a strict signed 64-bit integer: booleans,
floats, strings and overflow are rejected. Omitting it preserves the prior request
body; zero is forwarded. HTTP chat-completion paths pass it unchanged in streaming
and non-streaming payloads. The existing benchmark accepts `--seed` and uses the
same value for first, warmup and measured requests, recording the requested settings.
Ollama documents [seed support](https://docs.ollama.com/api/openai-compatibility),
and vLLM's [request schema](https://docs.vllm.ai/en/latest/api/vllm/entrypoints/openai/chat_completion/protocol/)
defines the same integer range. Provider/artifact/cache/engine-specific determinism
still requires qualification; a requested seed alone is not proof of identical output.

Simple ONNX now uses the existing HTTP transport and an explicit
`ONNX_LLM_ENDPOINT` (`/v1` base) for the isolated CUDA worker. Disabled `ONNX_LLM_ENABLED` or a missing endpoint
returns 503 before model/adapter work; the API no longer initializes an ONNX LLM
or falls back to CPU in this route. Both modes preserve native usage and seed.
The worker checks its actual device in `/health`; runtime probing does not infer
readiness from merely selecting ONNX.

The pinned ORT GenAI 0.12.2 worker accepts strict signed64 seeds at its HTTP
boundary but rejects values outside native signed32 before tokenization with
`seed_out_of_native_range`. There is no truncation. Signed32 maps to the native
`random_seed` search option; `-1` selects random-device seeding, and omitted/null
leaves defaults unchanged. See the pinned [native field](https://github.com/microsoft/onnxruntime-genai/blob/v0.12.2/src/config.h#L344)
and [Python binding](https://github.com/microsoft/onnxruntime-genai/blob/v0.12.2/src/python/python.cpp#L168-L176).

This change qualifies neither the older ONNX activation/model-catalog code nor
the separate legacy task executor. Those paths still require migration before
Full ONNX, all-route lifecycle or task 266 can be considered complete.


## ONNX orchestration uses the same worker boundary

KernelBuilder registers the selected ONNX model as a native MAF HTTP service,
using only ONNX_LLM_ENDPOINT and the configured served model ID. AI_MODE=LOCAL,
local routing and multi-service registration retain that selection. Disabled ONNX
or an absent endpoint fails before creating a client, including multi-service mode.
A stale LLM_LOCAL_ENDPOINT never supplies an implicit Ollama/native fallback.

POST /tasks no longer substitutes a native ONNX process pool for orchestration.
Normal and Complex retain their policy, intent, context, tools and history paths;
Direct still uses Simple. Unsupported tools/structured output remain explicit
worker errors, rather than silently downgrading the requested workflow.
The compatibility task cleanup hook owns no model or process and does not prove
worker GPU release. Activation/catalog/controller migration and real API routing
qualification remain separate unfinished requirements of task266.
