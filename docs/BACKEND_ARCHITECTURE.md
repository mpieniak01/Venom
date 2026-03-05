# Backend Architecture (Model Management)

## Scope
This document describes the division of responsibilities in model management and the API router structure after refactor 76c.

## Division of Responsibilities

### ModelRegistry (venom_core/core/model_registry.py)
- Model discovery and catalog (registry: providers/trending/news).
- Model installation/removal through providers.
- Model metadata and capabilities (manifest, generation schema).
- Asynchronous model operations (ModelOperation).
- Does not execute I/O directly - uses adapters (clients).

### ModelManager (venom_core/core/model_manager.py)
- Lifecycle and versioning of local models.
- Resource guard (limits, usage metrics, offloading).
- Version activation and local model operations.

## I/O Adapters (clients)
- `venom_core/core/model_registry_clients.py`
  - `OllamaClient` - HTTP + CLI for ollama (list_tags, pull, remove).
  - `HuggingFaceClient` - HTTP (list, news) + snapshot download.

## Model API Routers
Routers are composed in `venom_core/api/routes/models.py` (aggregator). Submodules:
- `models_install.py` - /models, /models/install, /models/switch, /models/{model_name}
- `models_usage.py` - /models/usage, /models/unload-all
- `models_registry.py` - /models/providers, /models/trending, /models/news
- `models_registry_ops.py` - /models/registry/install, /models/registry/{model_name}, /models/activate, /models/operations
- `models_config.py` - /models/{model_name}/capabilities, /models/{model_name}/config
- `models_remote.py` - /models/remote/providers, /models/remote/catalog, /models/remote/connectivity, /models/remote/validate
- `models_translation.py` - /translate

## Router Layering Contract (PR 183)
To keep API adapters thin and testable, routers in `venom_core/api/routes/*` should follow this contract:

- Router = HTTP adapter only (request parsing, status codes, response mapping).
- Operational/use-case logic lives in `venom_core/services/*`.
- New direct imports from `venom_core.core.*` and `venom_core.infrastructure.*` in routers are disallowed by default.
- Side-effect libraries in routers (`subprocess`, `httpx`, `threading`) are restricted and guarded.

Reference implementations introduced during PR 183:
- `venom_core/services/knowledge_route_service.py`
- `venom_core/services/knowledge_lessons_service.py`
- `venom_core/services/tasks_service.py`
- `venom_core/services/tasks_onnx_service.py`
- `venom_core/services/llm_simple_transport.py`
- `venom_core/services/llm_simple_stream_service.py`

Architecture guard tests:
- `tests/test_api_routes_import_guard.py`

## Runtime and model routing
- `venom_core/execution/model_router.py` and `venom_core/core/model_router.py` – routing between local LLM and cloud (LOCAL/HYBRID/CLOUD).
- `venom_core/core/llm_server_controller.py` – LLM server control (Ollama/vLLM/ONNX) and health checks.
- `venom_core/core/generation_params_adapter.py` – maps generation params to OpenAI/vLLM/Ollama/ONNX formats.
- Runtime configuration lives in `venom_core/config.py` and `.env` (e.g. `LLM_LOCAL_ENDPOINT`, `VLLM_ENDPOINT`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`).

### Unified runtime options contract (PR 185)
- `GET /api/v1/system/llm-runtime/options` is the canonical UI contract for runtime/model selectors.
- Response includes:
  - active runtime snapshot (`active_server`, `active_model`, `config_hash`, `source_type`),
  - local + cloud runtime targets (`ollama`, `vllm`, `onnx`, `openai`, `google`),
  - model lists scoped per runtime target.
- `POST /api/v1/system/llm-runtime/active` enforces provider/model pairing for cloud runtime:
  - requested model must belong to selected provider catalog,
  - invalid pair returns `400` with explicit error message.
- `GET /api/v1/system/llm-servers` remains a local-runtime technical endpoint; operational UI flows (Chat + Models) should use `llm-runtime/options`.

### Feedback-loop alias resolution (PR 187)
- Product alias class for coding feedback-loop:
  - `requested_alias`: `OpenCodeInterpreter-Qwen2.5-7B`
  - `primary`: `qwen2.5-coder:7b`
  - `fallbacks`: `qwen2.5-coder:3b`, `codestral:latest`
- Runtime options (`GET /api/v1/system/llm-runtime/options`) now expose:
  - active resolution fields: `requested_model_alias`, `resolved_model_id`, `resolution_reason`,
  - model-level metadata: `feedback_loop_ready`, `feedback_loop_tier`,
  - feedback-loop status block with `requested_alias`, `primary`, `fallbacks`.
- Local runtime activation (`POST /api/v1/system/llm-servers/active`) supports:
  - optional `model_alias` and `exact_only`,
  - explicit resolution payload (`requested_model_alias`, `resolved_model_id`, `resolution_reason`),
  - resource guard for 7B with safe fallback (or explicit error when `exact_only=true`).
- Model install (`POST /api/v1/models/install`) supports feedback-loop alias flow:
  - idempotent install (skip when already present),
  - retry + timeout aware pull orchestration,
  - guard-aware candidate plan (`primary` or fallback chain).

### Unified model catalog contract (PR 191C)
- Canonical contract for runtime/model selectors: `GET /api/v1/system/llm-runtime/options`.
- `model_catalog.trainable_models` carries:
  - training execution location: `source_type` (`local` | `cloud`),
  - cost classification: `cost_tier` (`free` | `paid` | `unknown`),
  - stable backend ordering key: `priority_bucket`,
  - inference compatibility map: `runtime_compatibility` (`{ [runtime_id]: boolean }`),
  - optional preferred target for inference: `recommended_runtime`.
- Ordering policy is backend-authoritative (UI only renders backend order):
  - `local + installed_local` -> `local` -> `cloud free` -> `cloud unknown` -> `cloud paid`.
- Runtime compatibility must be derived from actually available local stack/catalog, not from hardcoded runtime keys.
- Adapter activation (`POST /api/v1/academy/adapters/activate`) includes compatibility validation:
  - optional `runtime_id` input,
  - rejects incompatible `base_model + adapter + runtime` with `400`.

## Execution Layer (Skills & MCP)
Integrated with Microsoft Semantic Kernel, enabling agent capabilities expansion:
- `venom_core/execution/skills/base_skill.py` – Base class for all skills.
- `venom_core/skills/mcp_manager_skill.py` – MCP tools management (Git import, venv).
- `venom_core/skills/mcp/proxy_generator.py` – Automatic proxy code generation for MCP servers.
- `venom_core/skills/custom/` – Runtime-generated skills directory (may be absent on fresh checkout until first MCP import).

## Related documentation (MCP)
- `docs/DEV_GUIDE_SKILLS.md` – MCP import and Skills standards.
- `docs/TREE.md` – repo structure and MCP directories.

## API Contracts
Endpoint paths remain unchanged. Refactor concerns only code structure.

## Chat routing (consistency note)
Chat modes (Direct/Normal/Complex) and routing/intent rules are described in `docs/CHAT_SESSION.md`.

## Performance Optimizations (v2026-02)
### Fast Path (Template Response)
- **Logic**: Static intents (`HELP_REQUEST`, `TIME_REQUEST`, `INFRA_STATUS`) bypass heavy context building (memory/history) for sub-100ms latency.
- **Route**: `Orchestrator._run_task_fastpath`.
- **UTC Standardization**: All internal timestamps are forced to UTC in `tracer.py` and `models.py` to ensure consistency across services and correct UI "relative time" labels.

### Background Processing
- **ResultProcessor**: Non-critical operations (Vector Store upsert, RL logs) are offloaded to background tasks to unblock UI response.
### Backend IO / Storage
- **Debouncing**: `StateManager`, `RequestTracer`, and `SessionStore` use write-debouncing to minimize disk I/O.
- **Session Persistence**: `SessionStore` preserves chat history across backend restarts by updating `boot_id` instead of clearing sessions.
- **Ollama Optimization**: Added `LLM_KEEP_ALIVE` setting to prevent model unloading, significantly reducing TTFT in Direct mode.
- **Clean Shutdown**: `make stop` explicitly unloads models from VRAM using `keep_alive: 0`, ensuring system returns to a clean state.
