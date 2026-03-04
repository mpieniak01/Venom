# Model Tuning - System Strojenia Parametrów

## Przegląd

System strojenia parametrów (Model Tuning) umożliwia użytkownikowi dynamiczną konfigurację parametrów inferencji modeli AI. Pozwala to na kontrolowanie "kreatywności" i zachowania modelu poprzez interfejs, który automatycznie dostosowuje się do możliwości wybranego modelu.

Uwaga zakresowa:
- Ten dokument opisuje **strojenie parametrów inferencji** (`generation_params`).
- Selekcja modelu bazowego LoRA/QLoRA i lifecycle adapterów są obsługiwane przez API Academy (`/api/v1/academy/*`) i opisane w `docs/PL/THE_ACADEMY.md`.

## Architektura

### Backend (venom_core)

#### 1. Definicja Schematów Parametrów

**GenerationParameter** - dataclass definiujący pojedynczy parametr:
```python
@dataclass
class GenerationParameter:
    type: str  # "float", "int", "bool", "list", "enum"
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    desc: Optional[str] = None
    options: Optional[List[Any]] = None
```

**ModelCapabilities** - rozszerzony o pole `generation_schema`:
```python
@dataclass
class ModelCapabilities:
    # ... inne pola ...
    generation_schema: Optional[Dict[str, GenerationParameter]] = None
```

#### 2. Domyślne Parametry

Funkcja `_create_default_generation_schema()` zwraca standardowy zestaw parametrów:
- **temperature** (float, 0.0-2.0, default: 0.7) - Kreatywność modelu
- **max_tokens** (int, 128-8192, default: 2048) - Maksymalna liczba tokenów
- **top_p** (float, 0.0-1.0, default: 0.9) - Nucleus sampling
- **top_k** (int, 1-100, default: 40) - Top-K sampling
- **repeat_penalty** (float, 1.0-2.0, default: 1.1) - Kara za powtarzanie

#### 3. Specjalne Konfiguracje Modeli

**Llama 3** - temperatura ograniczona do 0.0-1.0:
```python
if "llama" in name.lower() and "3" in name:
    generation_schema["temperature"] = GenerationParameter(
        type="float",
        default=0.7,
        min=0.0,
        max=1.0,
        desc="Kreatywność modelu (0 = deterministyczny, 1 = kreatywny)",
    )
```

#### 4. API Endpoint

**GET /api/v1/models/{model_name}/config**

Zwraca schemat parametrów dla danego modelu:
```json
{
  "success": true,
  "model_name": "llama3",
  "generation_schema": {
    "temperature": {
      "type": "float",
      "default": 0.7,
      "min": 0.0,
      "max": 1.0,
      "desc": "Kreatywność modelu (0 = deterministyczny, 1 = kreatywny)"
    },
    "max_tokens": {
      "type": "int",
      "default": 2048,
      "min": 128,
      "max": 8192,
      "desc": "Maksymalna liczba tokenów w odpowiedzi"
    }
  }
}
```

#### 5. Przekazywanie Parametrów

**TaskRequest** rozszerzony o pole `generation_params`:
```python
class TaskRequest(BaseModel):
    content: str
    store_knowledge: bool = True
    generation_params: Optional[Dict[str, Any]] = None
```

### Frontend (web-next)

#### 1. Komponent DynamicParameterForm

Inteligentny komponent renderujący UI na podstawie schematu z backendu:

**Typy kontrolek:**
- **float/int** → Suwak (slider) + Input numeryczny
- **bool** → Przełącznik (Toggle Switch)
- **list/enum** → Dropdown (Select)

**Użycie:**
```tsx
<DynamicParameterForm
  schema={generationSchema}
  values={currentValues}
  onChange={(values) => setGenerationParams(values)}
  onReset={() => setGenerationParams(null)}
/>
```

#### 2. Integracja z Cockpit

**Przycisk Tuning** - otwiera drawer z formularzem:
```tsx
<Button onClick={handleOpenTuning}>
  <Settings className="h-4 w-4 mr-1" />
  Tuning
</Button>
```

**Drawer (Sheet)** - panel z prawej strony z formularzem parametrów.

#### 3. Wysyłanie Zadań

Parametry przekazywane w `sendTask()`:
```typescript
await sendTask(content, storeKnowledge, generationParams);
```

Payload do API:
```json
{
  "content": "Napisz funkcję...",
  "store_knowledge": true,
  "generation_params": {
    "temperature": 0.5,
    "max_tokens": 1024,
    "top_p": 0.95
  }
}
```

## Relacja do flow LoRA w Academy

Strojenie inferencji i trening Academy są powiązane, ale to osobne kontrakty:

1. Selektor modelu bazowego Academy używa:
   - `GET /api/v1/academy/models/trainable`
2. Selekcja runtime/modelu w Chat używa:
   - `GET /api/v1/system/llm-runtime/options`
3. Aktywacja adaptera może zawierać walidację runtime:
   - `POST /api/v1/academy/adapters/activate` z opcjonalnym `runtime_id`
   - opcjonalne `deploy_to_chat_runtime=true`, aby wdrożyć aktywny adapter do runtime Chat

Kluczowe pola kontraktu Academy:
- `source_type`: gdzie wykonywany jest trening (`local` lub `cloud`), nie skąd pochodzi model.
- `runtime_compatibility`: mapa runtime, na których adapter po treningu może działać.
- `recommended_runtime`: preferowany runtime dla inferencji adaptera.

Praktyczna sekwencja:
1. Wybierz treningowalny model bazowy w Academy.
2. Wytrenuj adapter.
3. W Chat przełącz runtime kompatybilny z tym modelem/adapterem.
4. Aktywuj adapter (opcjonalnie z `runtime_id`), żeby wymusić walidację kompatybilności.
5. Gdy `deploy_to_chat_runtime=true`, Academy może automatycznie przełączyć model Chat dla adapterów Ollama.

Aktualne ograniczenie:
1. Automatyczny deploy/rollback adaptera do runtime Chat jest obecnie zaimplementowany dla `ollama`.
2. Deploy/rollback dla `vllm` i `onnx` jest zaplanowany jako follow-up.

## Użycie

### Dla Użytkownika

1. Otwórz interfejs Cockpit
2. Kliknij przycisk **"Tuning"** (ikona ustawień)
3. W otwartym drawerze dostosuj parametry:
   - Przesuń suwaki (temperature, max_tokens, etc.)
   - Przełącz opcje bool
   - Wybierz opcje z dropdownów
4. Kliknij **"Resetuj"** aby przywrócić domyślne wartości
5. Zamknij drawer - ustawienia zostaną zapamiętane
6. Wyślij zadanie - parametry zostaną automatycznie dołączone

### Dla Developera

#### Dodanie Nowego Parametru

1. Zaktualizuj `_create_default_generation_schema()` w `model_registry.py`:
```python
def _create_default_generation_schema():
    return {
        # ... istniejące parametry ...
        "presence_penalty": GenerationParameter(
            type="float",
            default=0.0,
            min=-2.0,
            max=2.0,
            desc="Kara za obecność tokenu w tekście",
        ),
    }
```

2. Frontend automatycznie renderuje nowy parametr

#### Konfiguracja dla Specyficznego Modelu

Edytuj manifest modelu (`data/models/manifest.json`):
```json
{
  "models": [
    {
      "name": "custom-model",
      "provider": "ollama",
      "capabilities": {
        "generation_schema": {
          "temperature": {
            "type": "float",
            "default": 0.8,
            "min": 0.0,
            "max": 1.5,
            "desc": "Custom temperature range"
          }
        }
      }
    }
  ]
}
```

## Kryteria Akceptacji

- ✅ Dla modelu "Llama 3" suwak temperatury ma zakres 0.0-1.0
- ✅ Dla modelu specyficznego pojawiają się dodatkowe opcje jeśli zdefiniowane w manifeście
- ✅ Runtime-aware mapping parametrów jest realizowany przez `GenerationParamsAdapter` (Ollama/vLLM/ONNX/OpenAI)
- ⚠️ Realny wpływ zależy od wsparcia danego parametru przez wybrany runtime/provider

## Status Implementacji

### Zrealizowane
- ✅ Backend: GenerationParameter i ModelCapabilities
- ✅ Backend: Endpoint /api/v1/models/{name}/config
- ✅ Backend: TaskRequest z generation_params
- ✅ Backend: mapowanie `GenerationParamsAdapter` (`max_tokens` -> `num_predict` dla Ollama, `repeat_penalty` -> `repetition_penalty` dla vLLM/ONNX)
- ✅ Backend: runtime/model overrides przez `MODEL_GENERATION_OVERRIDES`
- ✅ Frontend: DynamicParameterForm z dynamicznym renderowaniem
- ✅ Frontend: Przycisk Tuning i Drawer
- ✅ Frontend: Przekazywanie parametrów do API

### Do Zrealizowania
- ⚠️ Macierz weryfikacji E2E wpływu parametrów między runtime (Ollama/vLLM/ONNX/cloud)
- ⚠️ Presety/profile UX do ponownego użycia konfiguracji

## Przykład Użycia

```python
# Backend - definicja schematu
schema = {
    "temperature": GenerationParameter(
        type="float", default=0.7, min=0.0, max=1.0
    )
}

# API Request
POST /api/v1/tasks
{
    "content": "Napisz funkcję sortującą",
    "generation_params": {
        "temperature": 0.3,  # deterministyczny
        "max_tokens": 512
    }
}

# Frontend - użycie komponentu
<DynamicParameterForm
    schema={schema}
    onChange={handleParamsChange}
/>
```

## Troubleshooting

**Problem:** Model nie ma zdefiniowanego schematu
**Rozwiązanie:** Dodaj `generation_schema` w manifeście modelu lub użyj domyślnego

**Problem:** Parametry nie wpływają na odpowiedź
**Rozwiązanie:** Zweryfikuj czy aktywny runtime/model wspiera dany parametr i sprawdź mapowanie runtime-specyficzne w `GenerationParamsAdapter`

**Problem:** UI nie renderuje niektórych typów parametrów
**Rozwiązanie:** Sprawdź czy typ parametru jest obsługiwany (float, int, bool, list, enum)

## Roadmap

1. **Faza 1** (Zrealizowana) - Backend schema + Frontend UI
2. **Faza 2** (W toku) - Walidacja E2E efektu parametrów między runtime
3. **Faza 3** (Przyszłość) - Profile parametrów (zapisywanie ulubionych ustawień)
4. **Faza 4** (Przyszłość) - A/B testing parametrów
