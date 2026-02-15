# Model Management System - Venom

## Overview

The model management system in Venom provides a centralized, automated way to install, remove, and switch AI models. It supports three domain types:
- **Local Runtime**: Models running locally via Ollama or vLLM.
- **Cloud API**: Models accessed via external APIs (OpenAI, Google Gemini).
- **Integrator Catalog**: Models available for download/installation (HuggingFace, Ollama Library).

## Architecture

### Components

1. **ModelRegistry** (`venom_core/core/model_registry.py`)
   - Central model registry
   - Metadata management (`manifest.json`)
   - Async operation queue

2. **Model Providers**
   - `OllamaModelProvider` - GGUF models via Ollama
   - `HuggingFaceModelProvider` - models from HuggingFace Hub

3. **API Endpoints** (`venom_core/api/routes/models.py`)
   - REST API for model management
   - Operation monitoring
   - Capabilities retrieval

4. **Runtime Controllers**
   - `LlmServerController` - vLLM/Ollama server control
   - systemd integration
   - health checks

## Usage

### API Endpoints

#### List available models

```bash
GET /api/v1/models/providers?provider=huggingface&limit=20
```

Response:
```json
{
  "success": true,
  "models": [
    {
      "provider": "huggingface",
      "model_name": "google/gemma-2b-it",
      "display_name": "gemma-2b-it",
      "size_gb": null,
      "runtime": "vllm",
      "tags": ["text-generation"],
      "downloads": 123456,
      "likes": 420
    }
  ],
  "count": 1
}
```

#### Trending models

```bash
GET /api/v1/models/trending?provider=ollama&limit=12
```

Response:
```json
{
  "success": true,
  "provider": "ollama",
  "models": [
    {
      "provider": "ollama",
      "model_name": "llama3:latest",
      "display_name": "llama3:latest",
      "size_gb": 4.1,
      "runtime": "ollama",
      "tags": ["llama", "8B"],
      "downloads": null,
      "likes": null
    }
  ],
  "count": 1,
  "stale": false,
  "error": null
}
```

#### News (HuggingFace Blog RSS)

```bash
GET /api/v1/models/news?provider=huggingface&limit=5&type=blog
```

Response:
```json
{
  "success": true,
  "provider": "huggingface",
  "items": [
    {
      "title": "New publication",
      "url": "https://huggingface.co/papers/...",
      "summary": "Publication summary...",
      "published_at": "2025-12-20",
      "authors": ["Author 1", "Author 2"],
      "source": "huggingface"
    }
  ],
  "count": 1,
  "stale": false,
  "error": null
}
```

#### Papers (HuggingFace Papers Month)

```bash
GET /api/v1/models/news?provider=huggingface&limit=5&type=papers&month=2025-12
```

Response:
```json
{
  "success": true,
  "provider": "huggingface",
  "items": [
    {
      "title": "New paper",
      "url": "https://huggingface.co/papers/2512.00001",
      "summary": "Paper summary...",
      "published_at": "2025-12-01T12:00:00.000Z",
      "authors": ["Author 1", "Author 2"],
      "source": "huggingface"
    }
  ],
  "count": 1,
  "stale": false,
  "error": null
}
```

#### Install a model

```bash
POST /api/v1/models/registry/install
Content-Type: application/json

{
  "name": "llama3:latest",
  "provider": "ollama",
  "runtime": "ollama"
}
```

Response:
```json
{
  "success": true,
  "operation_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Model installation started: llama3:latest"
}
```

#### Check operation status

```bash
GET /api/v1/models/operations/550e8400-e29b-41d4-a716-446655440000
```

Response:
```json
{
  "success": true,
  "operation": {
    "operation_id": "550e8400-e29b-41d4-a716-446655440000",
    "model_name": "llama3:latest",
    "operation_type": "install",
    "status": "in_progress",
    "progress": 45.0,
    "message": "Downloading model layers..."
  }
}
```

#### Activate a model

```bash
POST /api/v1/models/activate
Content-Type: application/json

{
  "name": "llama3:latest",
  "runtime": "ollama"
}
```

#### Remove a model

```bash
DELETE /api/v1/models/registry/llama3:latest
```

#### Model capabilities

```bash
GET /api/v1/models/google%2Fgemma-2b-it/capabilities
```

Response:
```json
{
  "success": true,
  "model_name": "google/gemma-2b-it",
  "capabilities": {
    "supports_system_role": false,
    "supports_function_calling": false,
    "allowed_roles": ["user", "assistant"],
    "prompt_template": null,
    "max_context_length": 4096,
    "quantization": null
  }
}
```

### Python API

```python
from venom_core.core.model_registry import ModelRegistry, ModelProvider

# Init
registry = ModelRegistry(models_dir="./data/models")

# List available models
models = await registry.list_available_models(provider=ModelProvider.OLLAMA)

# Install a model
operation_id = await registry.install_model(
    model_name="llama3:latest",
    provider=ModelProvider.OLLAMA,
    runtime="ollama"
)

# Check status
operation = registry.get_operation_status(operation_id)
print(f"Status: {operation.status}, Progress: {operation.progress}%")

# Remove model
operation_id = await registry.remove_model("llama3:latest")

# Activate model
success = await registry.activate_model("llama3:latest", "ollama")
```

## Model Capabilities

The system tracks model capabilities via manifests:

### System role support

Some models (e.g., Gemma) do not support the `system` role. ModelRegistry stores this:

```python
capabilities = registry.get_model_capabilities("google/gemma-2b-it")
if not capabilities.supports_system_role:
    # Adapt prompt - remove system message or convert to user message
    pass
```

### Prompt templates

Models may require specific chat templates:

```json
{
  "prompt_template": "<|im_start|>user\n{message}<|im_end|>\n<|im_start|>assistant\n"
}
```

### Quantization

Quantization info (Q4_K_M, Q8_0, etc.):

```json
{
  "quantization": "Q4_K_M"
}
```

## Runtime Management

### Active runtime and model

The system keeps one active LLM runtime at a time (Ollama or vLLM) and remembers the last model per runtime. Current state:

```bash
GET /api/v1/system/llm-servers/active
```

### Cloud runtime (OpenAI/Gemini)

Alias with full payload of active runtime:

```bash
GET /api/v1/system/llm-runtime/active
```

Switch runtime to cloud provider (used by `/gpt` and `/gem`):

```bash
POST /api/v1/system/llm-runtime/active
Content-Type: application/json

{
  "provider": "openai",
  "model": "gpt-4o-mini"
}
```

Notes:
- `provider`: `openai` or `google` (aliases: `gem`, `google-gemini`).
- Endpoint updates `LLM_SERVICE_TYPE`, `LLM_MODEL_NAME`, `ACTIVE_LLM_SERVER`.
- Requires active API key (`OPENAI_API_KEY` or `GOOGLE_API_KEY`).

## Cache and Offline Mode

Backend caches trending lists and model catalogs for 30 minutes. Without Internet, endpoints return the last cached result with `stale: true` and optional `error`.

UI also caches trends and the catalog in `localStorage` and does not auto-refresh after Next.js restart. Refresh only via “Refresh trends” and “Refresh catalog”.

`models/news` uses the public HuggingFace RSS `https://huggingface.co/blog/feed.xml` (no token).
`type=papers` parses HTML from `https://huggingface.co/papers/month/YYYY-MM` (no official RSS), so it depends on page structure.
News/papers translation uses the active model, but for long texts only the initial fragment is translated to keep response times stable. Planned: chunking long texts for full translation.

### Test scenarios (News / Papers)
1. **News - cache per language**
   - Set panel language (PL/EN/DE), refresh News.
   - Expected: correct translation + `localStorage` cache keyed by language.
2. **Papers - partial translation**
   - Refresh Papers, verify summary is shortened and translated.
   - Expected: no 500s, stable response times.
3. **UI**
   - Check “View” buttons in News and Papers (frame, consistent style).
   - Check accordions and manual refresh per section.

## Translation Tool

Backend exposes a generic translation endpoint based on the active runtime/model:

```bash
POST /api/v1/translate
Content-Type: application/json

{
  "text": "Hello world",
  "source_lang": "en",
  "target_lang": "pl",
  "use_cache": true
}
```

Response:
```json
{
  "success": true,
  "translated_text": "Witaj świecie",
  "target_lang": "pl"
}
```

Notes:
- Supported languages: `pl`, `en`, `de`.
- News/papers translation uses this mechanism.
- Long content is currently translated in fragments (short description) for stability.

### Test scenarios (Translation Tool)
1. **Basic translation**
   - Send `/api/v1/translate` with short text.
   - Expected: correct translation in response.
2. **Target language**
   - Test `pl`, `en`, `de`.
   - Expected: consistent response format, no 400/500 errors.
3. **Invalid data**
   - Send unsupported `target_lang` (e.g., `fr`).
   - Expected: HTTP 400 validation error.

Switch runtime + activate model:

```bash
POST /api/v1/system/llm-servers/active
Content-Type: application/json

{
  "server_name": "ollama",
  "model_name": "phi3:mini"
}
```

Backend stops other runtimes and validates that the model exists on the selected server.

### Systemd Integration

Scripts detect and use systemd if configured:

```bash
# Check status
systemctl status vllm.service
systemctl status ollama.service

# Restart
systemctl restart vllm.service
```

See `scripts/systemd/README.md` for details.

### Local processes

If systemd is unavailable, scripts run in local process mode:

```bash
# Start
bash scripts/llm/vllm_service.sh start
bash scripts/llm/ollama_service.sh start

# Stop (graceful shutdown)
bash scripts/llm/vllm_service.sh stop
```

### Graceful Shutdown

Scripts implement graceful shutdown:

1. SIGTERM - normal stop attempt (wait 2s)
2. SIGKILL - force stop if unresponsive
3. Cleanup zombie processes

### Zombie Process Prevention

- `LimitCORE=0` in systemd (no core dumps)
- Cleanup on stop (pkill zombie processes)
- PID tracking in `.pid` files

## Manifest System

### Manifest structure

`data/models/manifest.json`:

```json
{
  "models": [
    {
      "name": "llama3:latest",
      "provider": "ollama",
      "display_name": "Llama 3 Latest",
      "size_gb": 4.5,
      "status": "installed",
      "capabilities": {
        "supports_system_role": true,
        "allowed_roles": ["system", "user", "assistant"],
        "max_context_length": 8192
      },
      "local_path": null,
      "sha256": null,
      "installed_at": "2024-12-17T10:00:00",
      "runtime": "ollama"
    }
  ],
  "updated_at": "2024-12-17T10:00:00"
}
```

### Auto-update

Manifest is automatically updated on:
- model installation
- model removal
- metadata changes

## Security

### Validation

- Model name validation (regex: `^[\w\-.:\/]+$`)
- Path traversal protection
- Storage quota checks

### Resource Limits

```python
# Default limits
MAX_STORAGE_GB = 50  # Max storage for models
DEFAULT_MODEL_SIZE_GB = 4.0  # Estimated size for Resource Guard
```

### Locks

Operations on the same runtime are serialized:

```python
# Per-runtime locks
_runtime_locks: Dict[str, asyncio.Lock] = {
    "vllm": asyncio.Lock(),
    "ollama": asyncio.Lock(),
}
```

## Monitoring

### Usage metrics

```bash
GET /api/v1/models/usage
```

Response:
```json
{
  "success": true,
  "usage": {
    "disk_usage_gb": 12.5,
    "disk_limit_gb": 50,
    "disk_usage_percent": 25.0,
    "cpu_usage_percent": 45.2,
    "memory_total_gb": 16.0,
    "memory_used_gb": 8.5,
    "memory_usage_percent": 53.1,
    "gpu_usage_percent": 75.0,
    "vram_usage_mb": 5120,
    "vram_total_mb": 10240,
    "vram_usage_percent": 50.0,
    "models_count": 3
  }
}
```

### Operations History

```bash
GET /api/v1/models/operations?limit=10
```

List of recent operations with statuses and errors.

## Best Practices

### 1. Check storage before installation

```python
if not registry.check_storage_quota(additional_size_gb=5.0):
    print("Not enough disk space!")
```

### 2. Monitor long-running operations

```python
operation_id = await registry.install_model(...)

while True:
    op = registry.get_operation_status(operation_id)
    if op.status in [OperationStatus.COMPLETED, OperationStatus.FAILED]:
        break
    print(f"Progress: {op.progress}%")
    await asyncio.sleep(5)
```

### 3. Use capabilities when building prompts

```python
caps = registry.get_model_capabilities(model_name)
if not caps.supports_system_role:
    # Convert system message to a user prefix
    user_message = f"Instructions: {system_message}\n\nUser: {user_input}"
```

### 4. Graceful degradation when no models

```python
models = await registry.list_available_models()
if not models:
    # Fallback to cloud provider or inform about missing models
    pass
```

## Troubleshooting

### Problem: Model not installing

**Diagnosis:**
```bash
GET /api/v1/models/operations/{operation_id}
```

Check the `error` field in response.

**Solutions:**
- No disk space: remove unused models
- No internet: verify connection
- Invalid name: verify provider name

### Problem: Runtime fails to start

**Diagnosis:**
```bash
# Check logs
tail -f logs/vllm.log
tail -f logs/ollama.log

# Check systemd
systemctl status vllm.service
journalctl -u vllm.service -n 50
```

**Solutions:**
- Wrong model path: verify `VLLM_MODEL_PATH`
- No GPU: lower `VLLM_GPU_MEMORY_UTILIZATION`
- Port in use: change `VLLM_PORT` / `OLLAMA_PORT`

### Problem: Zombie processes

**Diagnosis:**
```bash
ps aux | grep "vllm serve"
ps aux | grep "ollama serve"
```

**Solution:**
```bash
# Force cleanup
bash scripts/llm/vllm_service.sh stop
bash scripts/llm/ollama_service.sh stop

# Or direct kill
pkill -9 -f "vllm serve"
pkill -9 -f "ollama serve"
```

### Problem: Model capability not detected

**Diagnosis:**
```bash
GET /api/v1/models/{model_name}/capabilities
```

**Solution:**
Manually update manifest:

```python
caps = ModelCapabilities(
    supports_system_role=False,
    allowed_roles=["user", "assistant"]
)
metadata = ModelMetadata(
    name="model-name",
    provider=ModelProvider.OLLAMA,
    display_name="Display Name",
    capabilities=caps
)
registry.manifest["model-name"] = metadata
registry._save_manifest()
```

## Provider Governance and Observability

Venom includes a governance layer to manage costs, security, and reliability of LLM providers.

### Governance Features
- **Cost Limits**: Global and per-provider checks (Soft/Hard limits).
- **Rate Limits**: Request/Token limits per minute.
- **Fallback Policy**: Automated switching to backup providers on failure (Timeout, Auth Error, Budget Exceeded).
- **Secret Masking**: API keys are never logged or exposed in API responses.

For detailed rules and reason codes, see [Provider Governance](PROVIDER_GOVERNANCE.md).

### Observability
The system tracks metrics for every provider interaction:
- **Latency**: P50/P95/P99 response times.
- **Success Rate**: Error tracking with standardized `reason_code`.
- **Cost Tracking**: Real-time token usage and cost estimation.
- **Health Score**: Automated degradation detection.

## Future Enhancements

- [ ] Auto-discovery of models in `./models`
- [ ] Integration with HuggingFace Hub API (search, ratings)
- [ ] Model benchmarking (speed, quality metrics)
- [ ] Automatic model selection by task complexity
- [ ] Model versioning and rollback
- [ ] Distributed model storage (CDN/S3)
- [ ] Model compression and quantization automation
- [ ] Health monitoring with alerts
- [ ] WebSocket streaming for install progress
- [ ] Model usage statistics and analytics
