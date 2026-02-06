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
- `models_translation.py` - /translate

## Runtime and model routing
- `venom_core/execution/model_router.py` and `venom_core/core/model_router.py` – routing between local LLM and cloud (LOCAL/HYBRID/CLOUD).
- `venom_core/core/llm_server_controller.py` – LLM server control (Ollama/vLLM) and health checks.
- `venom_core/core/generation_params_adapter.py` – maps generation params to OpenAI/vLLM/Ollama formats.
- Runtime configuration lives in `venom_core/config.py` and `.env` (e.g. `LLM_LOCAL_ENDPOINT`, `VLLM_ENDPOINT`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`).

## Execution Layer (Skills & MCP)
Integrated with Microsoft Semantic Kernel, enabling agent capabilities expansion:
- `venom_core/execution/skills/base_skill.py` – Base class for all skills.
- `venom_core/skills/mcp_manager_skill.py` – MCP tools management (Git import, venv).
- `venom_core/skills/mcp/proxy_generator.py` – Automatic proxy code generation for MCP servers.
- `venom_core/skills/custom/` – Directory for dynamically generated and utility skills.

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
