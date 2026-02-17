# Model Management System - Venom

## Przegląd

System zarządzania modelami w Venom zapewnia centralny, zautomatyzowany sposób instalacji, usuwania i przełączania modeli AI. Obsługuje trzy typy domenowe:
- **Local Runtime**: Modele uruchamiane lokalnie przez Ollama lub vLLM.
- **Cloud API**: Modele dostępne przez zewnętrzne API (OpenAI, Google Gemini).
- **Integrator Catalog**: Modele dostępne do pobrania/instalacji (HuggingFace, Biblioteka Ollama).

## Profile Runtime (Jedna Paczka)

Projekt korzysta obecnie z jednej paczki instalacyjnej i profili wybieranych przez `VENOM_RUNTIME_PROFILE`:
1. `light`: backend + web-next + Ollama (Gemma), bez vLLM.
2. `llm_off`: backend + web-next, bez lokalnego runtime LLM (nadal można używać zewnętrznych providerów API, np. OpenAI/Gemini, po ustawieniu kluczy).
3. `full`: rozszerzony stack; dostępne są Ollama i vLLM.

Uwagi operacyjne:
1. W `light` runtime/API/UI udostępniają wyłącznie ścieżki lokalnego runtime Ollama.
2. vLLM pozostaje opcjonalny dla `full` i nie jest wymaganiem domyślnego onboardingu light.

## Bazowy runtime Ollama (v1.5 / zadanie 152)

Aktualna baza dla lokalnego runtime Venom:
1. **Docelowa linia Ollama**: `0.16.x` (stable).
2. **Domyślny profil single-user**: `balanced-12-24gb`.
3. **Źródło prawdy konfiguracji**: backend env/config (bez hardcodów w frontendzie).

Rekomendowane zmienne strojenia:
1. `VENOM_OLLAMA_PROFILE` (`balanced-12-24gb`, `low-vram-8-12gb`, `max-context-24gb-plus`)
2. `OLLAMA_CONTEXT_LENGTH`
3. `OLLAMA_NUM_PARALLEL`
4. `OLLAMA_MAX_QUEUE`
5. `OLLAMA_FLASH_ATTENTION`
6. `OLLAMA_KV_CACHE_TYPE`
7. `OLLAMA_KEEP_ALIVE`
8. `OLLAMA_LOAD_TIMEOUT`
9. `OLLAMA_NO_CLOUD` (opcjonalna polityka prywatności)

Użycie capabilities runtime w integracji Venom:
1. structured outputs: `format` / `response_format`,
2. tool calling: `tools` / `tool_choice`,
3. opcjonalny kanał reasoning: `think` (feature-gated).

Referencje operacyjne:
1. zmienne deploymentowe i przykłady: `docs/PL/DEPLOYMENT_NEXT.md`,
2. zakres implementacji i checklista review: `docs_dev/_to_do/152_aktualizacja_ollama_0_16_i_adaptacja_funkcji.md`.

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

#### Trendy modeli

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
      "title": "Nowa publikacja",
      "url": "https://huggingface.co/papers/...",
      "summary": "Opis publikacji...",
      "published_at": "2025-12-20",
      "authors": ["Autor 1", "Autor 2"],
      "source": "huggingface"
    }
  ],
  "count": 1,
  "stale": false,
  "error": null
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

### Aktywny runtime i model

System utrzymuje jeden aktywny runtime LLM na raz (Ollama lub vLLM) i pamięta
ostatni model per runtime. Aktualny stan pobierzesz z:

```bash
GET /api/v1/system/llm-servers/active
```

### Cloud runtime (OpenAI/Gemini)

Alias z pełnym payloadem aktywnego runtime:

```bash
GET /api/v1/system/llm-runtime/active
```

Przełączenie runtime na provider cloud (wykorzystywane m.in. przez `/gpt` i `/gem`):

```bash
POST /api/v1/system/llm-runtime/active
Content-Type: application/json

{
  "provider": "openai",
  "model": "gpt-4o-mini"
}
```

Uwagi:
- `provider`: `openai` lub `google` (aliasy: `gem`, `google-gemini`).
- Endpoint aktualizuje `LLM_SERVICE_TYPE`, `LLM_MODEL_NAME`, `ACTIVE_LLM_SERVER`.
- Wymaga aktywnego klucza API (`OPENAI_API_KEY` lub `GOOGLE_API_KEY`).

## Cache i tryb offline

Backend cache’uje listy trendów i katalogi modeli na 30 minut. W przypadku braku
Internetu endpointy zwracają ostatni wynik z cache z flagą `stale: true` oraz
opcjonalnym polem `error`.

UI dodatkowo cache’uje trendy i katalog modeli w `localStorage` i nie odświeża
ich automatycznie po restarcie serwera Next.js. Odświeżenie następuje tylko po
kliknięciu przycisków „Odśwież trendy” i „Odśwież katalog”.

Endpoint `models/news` korzysta z publicznego RSS HuggingFace
`https://huggingface.co/blog/feed.xml` i nie wymaga tokena.
Tryb `type=papers` parsuje dane z HTML `https://huggingface.co/papers/month/YYYY-MM`
(brak oficjalnego RSS), dlatego zależy od struktury strony.
Tłumaczenie treści news/papers używa aktywnego modelu, ale dla długich tekstów
aktualnie tłumaczony jest tylko początkowy fragment (skrócony opis), aby
utrzymać stabilność i limity czasu. Do zaplanowania: podział długich treści na
krótsze fragmenty i pełne tłumaczenie całego tekstu.

### Scenariusze testowe (Nowości / Gazeta)
1. **Nowości (News) - cache per język**
   - Ustaw język panelu (PL/EN/DE), odśwież Nowości.
   - Oczekiwane: poprawne tłumaczenie + cache `localStorage` z kluczem języka.
2. **Gazeta (Papers) - tłumaczenie fragmentu**
   - Odśwież Papers, sprawdź że opis jest skrócony i przetłumaczony.
   - Oczekiwane: brak 500, stabilne czasy odpowiedzi.
3. **UI**
   - Sprawdź przyciski „Zobacz” w Nowościach i Papers (ramka, spójny styl).
   - Sprawdź akordeony i ręczne odświeżanie tylko danej sekcji.

## Narzędzie tłumaczeń (Translation Tool)

Backend udostępnia uniwersalny endpoint tłumaczeń oparty o aktywny runtime/model:

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

Odpowiedź:
```json
{
  "success": true,
  "translated_text": "Witaj świecie",
  "target_lang": "pl"
}
```

Uwagi:
- Obsługiwane języki: `pl`, `en`, `de`.
- Tłumaczenia news/papers korzystają z tego mechanizmu.
- Długie treści są obecnie tłumaczone fragmentami (skrócony opis) dla stabilności.

### Scenariusze testowe (Translation Tool)
1. **Tłumaczenie podstawowe**
   - Wyślij `/api/v1/translate` z krótkim tekstem.
   - Oczekiwane: poprawne tłumaczenie w odpowiedzi.
2. **Język docelowy**
   - Testuj `pl`, `en`, `de`.
   - Oczekiwane: format odpowiedzi spójny, brak błędów 400/500.
3. **Błędne dane**
   - Wyślij nieobsługiwany `target_lang` (np. `fr`).
   - Oczekiwane: HTTP 400 z komunikatem walidacyjnym.

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
      "title": "Nowa publikacja",
      "url": "https://huggingface.co/papers/2512.00001",
      "summary": "Opis publikacji...",
      "published_at": "2025-12-01T12:00:00.000Z",
      "authors": ["Autor 1", "Autor 2"],
      "source": "huggingface"
    }
  ],
  "count": 1,
  "stale": false,
  "error": null
}
```

Przełączenie runtime + aktywacja modelu:

```bash
POST /api/v1/system/llm-servers/active
Content-Type: application/json

{
  "server_name": "ollama",
  "model_name": "phi3:mini"
}
```

Backend zatrzymuje inne runtime i waliduje, czy model istnieje na wybranym serwerze.

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

## Zarządzanie Providerami (Governance) i Obserwowalność

Venom zawiera warstwę governance do zarządzania kosztami, bezpieczeństwem i niezawodnością dostawców LLM.

### Funkcje Governance
- **Limity Kosztów**: Sprawdzanie globalne i per-provider (Limity Soft/Hard).
- **Rate Limits**: Limity zapytań/tokenów na minutę.
- **Polityka Fallback**: Automatyczne przełączanie na zapasowych dostawców w przypadku awarii (Timeout, Błąd Autoryzacji, Przekroczenie Budżetu).
- **Maskowanie Sekretów**: Klucze API nigdy nie są logowane ani zwracane w odpowiedziach API.

Szczegółowe zasady i kody przyczyny opisano w [Provider Governance](PROVIDER_GOVERNANCE.md).

### Obserwowalność
System śledzi metryki dla każdej interakcji z providerem:
- **Opóźnienia (Latency)**: Czasy odpowiedzi P50/P95/P99.
- **Wskaźnik Sukcesu**: Śledzenie błędów ze standardowym `reason_code`.
- **Śledzenie Kosztów**: Zużycie tokenów i estymacja kosztów w czasie rzeczywistym.
- **Health Score**: Automatyczne wykrywanie degradacji usług.

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
