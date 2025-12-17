# Model Management System - Venom

## Przegląd

System zarządzania modelami w Venom zapewnia centralny, zautomatyzowany sposób instalacji, usuwania i przełączania modeli AI z różnych źródeł (HuggingFace, Ollama). 

## Architektura

### Komponenty

1. **ModelRegistry** (`venom_core/core/model_registry.py`)
   - Centralny rejestr modeli
   - Zarządzanie metadanymi (manifest.json)
   - Kolejkowanie operacji async

2. **Model Providers**
   - `OllamaModelProvider` - modele GGUF z Ollama
   - `HuggingFaceModelProvider` - modele z HuggingFace Hub

3. **API Endpoints** (`venom_core/api/routes/models.py`)
   - REST API do zarządzania modelami
   - Monitoring operacji
   - Pobieranie capabilities

4. **Runtime Controllers**
   - `LlmServerController` - sterowanie serwerami vLLM/Ollama
   - Integracja z systemd
   - Health checks

## Używanie

### API Endpoints

#### Lista dostępnych modeli

```bash
GET /api/v1/models/providers?provider=huggingface
```

Response:
```json
{
  "success": true,
  "models": [
    {
      "name": "google/gemma-2b-it",
      "provider": "huggingface",
      "display_name": "Gemma 2B IT",
      "size_gb": 4.0,
      "status": "available",
      "runtime": "vllm",
      "capabilities": {
        "supports_system_role": false,
        "allowed_roles": ["user", "assistant"]
      }
    }
  ],
  "count": 1
}
```

#### Instalacja modelu

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
  "message": "Instalacja modelu llama3:latest rozpoczęta"
}
```

#### Sprawdzanie statusu operacji

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
    "message": "Pobieranie warstw modelu..."
  }
}
```

#### Aktywacja modelu

```bash
POST /api/v1/models/activate
Content-Type: application/json

{
  "name": "llama3:latest",
  "runtime": "ollama"
}
```

#### Usuwanie modelu

```bash
DELETE /api/v1/models/registry/llama3:latest
```

#### Capabilities modelu

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

# Inicjalizacja
registry = ModelRegistry(models_dir="./data/models")

# Lista dostępnych modeli
models = await registry.list_available_models(provider=ModelProvider.OLLAMA)

# Instalacja modelu
operation_id = await registry.install_model(
    model_name="llama3:latest",
    provider=ModelProvider.OLLAMA,
    runtime="ollama"
)

# Sprawdzenie statusu
operation = registry.get_operation_status(operation_id)
print(f"Status: {operation.status}, Progress: {operation.progress}%")

# Usuwanie modelu
operation_id = await registry.remove_model("llama3:latest")

# Aktywacja modelu
success = await registry.activate_model("llama3:latest", "ollama")
```

## Model Capabilities

System śledzi możliwości modeli poprzez manifesty:

### Obsługa ról systemowych

Niektóre modele (np. Gemma) nie wspierają roli `system`. ModelRegistry przechowuje tę informację:

```python
capabilities = registry.get_model_capabilities("google/gemma-2b-it")
if not capabilities.supports_system_role:
    # Dostosuj prompt - usuń system message lub przekształć na user message
    pass
```

### Szablony promptów

Modele mogą mieć specyficzne szablony czatu:

```json
{
  "prompt_template": "<|im_start|>user\n{message}<|im_end|>\n<|im_start|>assistant\n"
}
```

### Kwantyzacja

Informacja o kwantyzacji modelu (Q4_K_M, Q8_0, etc.):

```json
{
  "quantization": "Q4_K_M"
}
```

## Runtime Management

### Systemd Integration

Skrypty automatycznie wykrywają i używają systemd jeśli jest skonfigurowany:

```bash
# Sprawdzenie statusu
systemctl status vllm.service
systemctl status ollama.service

# Restart
systemctl restart vllm.service
```

Zobacz `scripts/systemd/README.md` dla szczegółów konfiguracji.

### Procesy lokalne

Jeśli systemd nie jest dostępny, skrypty działają w trybie procesów lokalnych:

```bash
# Start
bash scripts/llm/vllm_service.sh start
bash scripts/llm/ollama_service.sh start

# Stop (graceful shutdown)
bash scripts/llm/vllm_service.sh stop
```

### Graceful Shutdown

Skrypty implementują graceful shutdown:

1. SIGTERM - próba normalnego zatrzymania (wait 2s)
2. SIGKILL - wymuszenie zatrzymania jeśli proces nie odpowiada
3. Cleanup zombie processes

### Zombie Process Prevention

- `LimitCORE=0` w systemd (brak core dumps)
- Cleanup przy stop (pkill zombie processes)
- PID tracking w `.pid` files

## Manifest System

### Struktura manifestu

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

Manifest jest automatycznie aktualizowany przy:
- Instalacji modelu
- Usuwaniu modelu
- Zmianie metadanych

## Security

### Validation

- Walidacja nazw modeli (regex: `^[\w\-.:\/]+$`)
- Path traversal protection
- Sprawdzanie limitów przestrzeni dyskowej

### Resource Limits

```python
# Default limits
MAX_STORAGE_GB = 50  # Maksymalna przestrzeń na modele
DEFAULT_MODEL_SIZE_GB = 4.0  # Szacowany rozmiar dla Resource Guard
```

### Locks

Operacje na tym samym runtime są serializowane:

```python
# Per-runtime locks
_runtime_locks: Dict[str, asyncio.Lock] = {
    "vllm": asyncio.Lock(),
    "ollama": asyncio.Lock(),
}
```

## Monitoring

### Metryki użycia

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

Lista ostatnich operacji z ich statusami i błędami.

## Best Practices

### 1. Sprawdź dostępną przestrzeń przed instalacją

```python
if not registry.check_storage_quota(additional_size_gb=5.0):
    print("Brak miejsca na dysku!")
```

### 2. Monitoruj operacje długotrwałe

```python
operation_id = await registry.install_model(...)

while True:
    op = registry.get_operation_status(operation_id)
    if op.status in [OperationStatus.COMPLETED, OperationStatus.FAILED]:
        break
    print(f"Progress: {op.progress}%")
    await asyncio.sleep(5)
```

### 3. Używaj capabilities przy budowie promptów

```python
caps = registry.get_model_capabilities(model_name)
if not caps.supports_system_role:
    # Przekształć system message na prefix user message
    user_message = f"Instructions: {system_message}\n\nUser: {user_input}"
```

### 4. Graceful degradation przy braku modeli

```python
models = await registry.list_available_models()
if not models:
    # Fallback do cloud provider lub informacja o braku modeli
    pass
```

## Troubleshooting

### Problem: Model nie instaluje się

**Diagnoza:**
```bash
GET /api/v1/models/operations/{operation_id}
```

Sprawdź pole `error` w response.

**Rozwiązania:**
- Brak miejsca: Usuń nieużywane modele
- Brak internetu: Sprawdź połączenie
- Nieprawidłowa nazwa: Weryfikuj nazwę w provider

### Problem: Runtime nie startuje

**Diagnoza:**
```bash
# Sprawdź logi
tail -f logs/vllm.log
tail -f logs/ollama.log

# Sprawdź systemd
systemctl status vllm.service
journalctl -u vllm.service -n 50
```

**Rozwiązania:**
- Nieprawidłowa ścieżka modelu: Sprawdź `VLLM_MODEL_PATH`
- Brak GPU: Obniż `VLLM_GPU_MEMORY_UTILIZATION`
- Port zajęty: Zmień `VLLM_PORT` / `OLLAMA_PORT`

### Problem: Zombie processes

**Diagnoza:**
```bash
ps aux | grep "vllm serve"
ps aux | grep "ollama serve"
```

**Rozwiązanie:**
```bash
# Wymuś cleanup
bash scripts/llm/vllm_service.sh stop
bash scripts/llm/ollama_service.sh stop

# Lub bezpośrednio
pkill -9 -f "vllm serve"
pkill -9 -f "ollama serve"
```

### Problem: Model capability nie wykryte

**Diagnoza:**
```bash
GET /api/v1/models/{model_name}/capabilities
```

**Rozwiązanie:**
Ręcznie zaktualizuj manifest:

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

## Future Enhancements

- [ ] Auto-discovery modeli z katalogu `./models`
- [ ] Integracja z HuggingFace Hub API (search, ratings)
- [ ] Model benchmarking (speed, quality metrics)
- [ ] Automatic model selection based on task complexity
- [ ] Model versioning i rollback
- [ ] Distributed model storage (CDN/S3)
- [ ] Model compression i quantization automation
- [ ] Health monitoring z alertami
- [ ] WebSocket streaming dla install progress
- [ ] Model usage statistics i analytics
