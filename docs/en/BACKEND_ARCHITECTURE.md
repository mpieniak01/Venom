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

## API Contracts
Endpoint paths remain unchanged. Refactor concerns only code structure.

## Chat routing (consistency note)
Chat modes (Direct/Normal/Complex) and routing/intent rules are described in `docs/en/CHAT_SESSION.md`.
