# Model Tuning - Parameter Tuning System

## Overview

The Model Tuning system enables users to dynamically configure AI model inference parameters. It allows control over model "creativity" and behavior through an interface that automatically adapts to the selected model's capabilities.

## Architecture

### Backend (venom_core)

#### 1. Parameter Schema Definition

**GenerationParameter** - dataclass defining a single parameter:
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

**ModelCapabilities** - extended with `generation_schema` field:
```python
@dataclass
class ModelCapabilities:
    # ... other fields ...
    generation_schema: Optional[Dict[str, GenerationParameter]] = None
```

#### 2. Default Parameters

Function `_create_default_generation_schema()` returns standard parameter set:
- **temperature** (float, 0.0-2.0, default: 0.7) - Model creativity
- **max_tokens** (int, 128-8192, default: 2048) - Maximum token count
- **top_p** (float, 0.0-1.0, default: 0.9) - Nucleus sampling
- **top_k** (int, 1-100, default: 40) - Top-K sampling
- **repeat_penalty** (float, 1.0-2.0, default: 1.1) - Repetition penalty

#### 3. Special Model Configurations

**Llama 3** - temperature limited to 0.0-1.0:
```python
if "llama" in name.lower() and "3" in name:
    generation_schema["temperature"] = GenerationParameter(
        type="float",
        default=0.7,
        min=0.0,
        max=1.0,
        desc="Model creativity (0 = deterministic, 1 = creative)",
    )
```

#### 4. API Endpoint

**GET /api/v1/models/{model_name}/config**

Returns parameter schema for given model:
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
      "desc": "Model creativity (0 = deterministic, 1 = creative)"
    },
    "max_tokens": {
      "type": "int",
      "default": 2048,
      "min": 128,
      "max": 8192,
      "desc": "Maximum number of tokens in response"
    }
  }
}
```

#### 5. Parameter Passing

**TaskRequest** extended with `generation_params` field:
```python
class TaskRequest(BaseModel):
    content: str
    store_knowledge: bool = True
    generation_params: Optional[Dict[str, Any]] = None
```

### Frontend (web-next)

#### 1. DynamicParameterForm Component

Intelligent component rendering UI based on backend schema:

**Control Types:**
- **float/int** → Slider + Numeric Input
- **bool** → Toggle Switch
- **list/enum** → Dropdown (Select)

**Usage:**
```tsx
<DynamicParameterForm
  schema={generationSchema}
  values={currentValues}
  onChange={(values) => setGenerationParams(values)}
  onReset={() => setGenerationParams(null)}
/>
```

#### 2. Cockpit Integration

**Tuning Button** - opens drawer with form:
```tsx
<Button onClick={handleOpenTuning}>
  <Settings className="h-4 w-4 mr-1" />
  Tuning
</Button>
```

**Drawer (Sheet)** - right-side panel with parameter form.

#### 3. Task Submission

Parameters passed in `sendTask()`:
```typescript
await sendTask(content, storeKnowledge, generationParams);
```

API Payload:
```json
{
  "content": "Write a function...",
  "store_knowledge": true,
  "generation_params": {
    "temperature": 0.5,
    "max_tokens": 1024,
    "top_p": 0.95
  }
}
```

## Usage

### For Users

1. Open Cockpit interface
2. Click **"Tuning"** button (settings icon)
3. In opened drawer, adjust parameters:
   - Move sliders (temperature, max_tokens, etc.)
   - Toggle bool options
   - Select options from dropdowns
4. Click **"Reset"** to restore default values
5. Close drawer - settings will be remembered
6. Submit task - parameters will be automatically included

### For Developers

#### Adding New Parameter

1. Update `_create_default_generation_schema()` in `model_registry.py`:
```python
def _create_default_generation_schema():
    return {
        # ... existing parameters ...
        "presence_penalty": GenerationParameter(
            type="float",
            default=0.0,
            min=-2.0,
            max=2.0,
            desc="Penalty for token presence in text",
        ),
    }
```

2. Frontend automatically renders new parameter

#### Configuration for Specific Model

Edit model manifest (`data/models/manifest.json`):
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

## Acceptance Criteria

- ✅ For "Llama 3" model, temperature slider has range 0.0-1.0
- ✅ For specific model, additional options appear if defined in manifest
- ⚠️ Parameter change in UI actually affects response (requires integration with LLMServerController)

## Implementation Status

### Completed
- ✅ Backend: GenerationParameter and ModelCapabilities
- ✅ Backend: Endpoint /api/v1/models/{name}/config
- ✅ Backend: TaskRequest with generation_params
- ✅ Frontend: DynamicParameterForm with dynamic rendering
- ✅ Frontend: Tuning Button and Drawer
- ✅ Frontend: Parameter passing to API

### To Be Completed
- ⚠️ Backend: Integration with LLMServerController
  - Parameter mapping for vLLM
  - Parameter mapping for Ollama (e.g., num_predict instead of max_tokens)
- ⚠️ Integration tests
- ⚠️ Verification of parameter impact on responses

## Usage Example

```python
# Backend - schema definition
schema = {
    "temperature": GenerationParameter(
        type="float", default=0.7, min=0.0, max=1.0
    )
}

# API Request
POST /api/v1/tasks
{
    "content": "Write a sorting function",
    "generation_params": {
        "temperature": 0.3,  # deterministic
        "max_tokens": 512
    }
}

# Frontend - component usage
<DynamicParameterForm
    schema={schema}
    onChange={handleParamsChange}
/>
```

## Troubleshooting

**Problem:** Model has no defined schema
**Solution:** Add `generation_schema` in model manifest or use default

**Problem:** Parameters don't affect response
**Solution:** Ensure LLMServerController passes parameters to LLM engine

**Problem:** UI doesn't render some parameter types
**Solution:** Check if parameter type is supported (float, int, bool, list, enum)

## Roadmap

1. **Phase 1** (Completed) - Backend schema + Frontend UI
2. **Phase 2** (To do) - Integration with LLMServerController
3. **Phase 3** (Future) - Parameter profiles (saving favorite settings)
4. **Phase 4** (Future) - A/B testing of parameters
