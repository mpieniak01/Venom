# Model Domain v2 - UI Implementation Guide

## Visual Implementation

### Model Card with Domain Badges

Each model card now displays three semantic badges:

```
┌─────────────────────────────────────────────────────┐
│  Llama 2 7B                           [vllm]       │
│  meta-llama/Llama-2-7b-hf                          │
│                                                     │
│  [Integrator Catalog] [LLM Engine] [Trainable]    │
│     (amber/yellow)      (emerald)     (green)      │
│                                                     │
│  Provider: huggingface                             │
│  Size: 13.50 GB                                    │
│  👍 1,200  ⬇️ 500,000                              │
│                                                     │
│  [text-generation] [llm] [pytorch]                 │
│                                                     │
│  [Install]                                         │
└─────────────────────────────────────────────────────┘
```

### Badge Color Scheme

#### Source Type Badges
- **Local Runtime** - `bg-blue-500/10 text-blue-300 border-blue-500/30`
  - For vLLM, locally running models
  
- **Cloud API** - `bg-purple-500/10 text-purple-300 border-purple-500/30`
  - For OpenAI, Gemini, Anthropic models
  
- **Integrator Catalog** - `bg-amber-500/10 text-amber-300 border-amber-500/30`
  - For HuggingFace, Ollama models

#### Model Role Badges
- **LLM Engine** - `bg-emerald-500/10 text-emerald-300 border-emerald-500/30`
  - For text generation models
  
- **Intent Embedding** - `bg-cyan-500/10 text-cyan-300 border-cyan-500/30`
  - For embedding models (bge, e5, sentence-transformers)

#### Trainability Badges
- **Trainable** - `bg-green-500/10 text-green-300 border-green-500/30`
  - Models that support LoRA/QLoRA training
  
- **Not Trainable** - `bg-zinc-500/10 text-zinc-400 border-zinc-500/30`
  - Models that cannot be trained
  - Includes tooltip with reason

### Example Cards

#### 1. Local Trainable LLM
```
┌─────────────────────────────────────────────┐
│  Llama 2 7B Chat                [vllm]     │
│  llama-2-7b-chat                           │
│                                            │
│  [Local Runtime] [LLM Engine] [Trainable] │
│                                            │
│  Provider: vllm                            │
│  Size: 13.50 GB                            │
└─────────────────────────────────────────────┘
```

#### 2. Cloud API (Not Trainable)
```
┌─────────────────────────────────────────────────────┐
│  GPT-4                                  [openai]   │
│  gpt-4                                             │
│                                                     │
│  [Cloud API] [LLM Engine] [Not Trainable]         │
│     ⓘ "Cloud API models cannot be trained locally" │
│                                                     │
│  Provider: openai                                  │
└─────────────────────────────────────────────────────┘
```

#### 3. Embedding Model
```
┌──────────────────────────────────────────────────────┐
│  BGE Large EN v1.5                    [vllm]        │
│  bge-large-en-v1.5                                  │
│                                                      │
│  [Integrator Catalog] [Intent Embedding] [Trainable]│
│                                                      │
│  Provider: huggingface                              │
│  Size: 1.34 GB                                      │
│  👍 4,500  ⬇️ 2,500,000                             │
└──────────────────────────────────────────────────────┘
```

#### 4. Ollama Model
```
┌────────────────────────────────────────────────┐
│  Mistral 7B Instruct         [ollama]        │
│  mistral:7b-instruct                         │
│                                              │
│  [Integrator Catalog] [LLM Engine] [Trainable]│
│                                              │
│  Provider: ollama                            │
│  Size: 4.10 GB                               │
│  👍 8,200  ⬇️ 1,200,000                      │
└────────────────────────────────────────────────┘
```

## i18n Labels

### English (en)
```typescript
domain: {
  sourceType: {
    label: "Source Type",
    "local-runtime": "Local Runtime",
    "cloud-api": "Cloud API",
    "integrator-catalog": "Integrator Catalog",
  },
  modelRole: {
    label: "Role",
    "llm-engine": "LLM Engine",
    "intent-embedding": "Intent Embedding",
  },
  trainability: {
    label: "Trainability",
    trainable: "Trainable",
    "not-trainable": "Not Trainable",
    badge: {
      trainable: "Trainable",
      notTrainable: "Not Trainable",
    },
    reasons: {
      notInCatalog: "Model not in Academy trainable catalog",
      notAvailable: "Trainability information not available",
      cloudOnly: "Cloud API models cannot be trained locally",
    },
  },
}
```

### Polish (pl)
```typescript
domain: {
  sourceType: {
    label: "Typ źródła",
    "local-runtime": "Środowisko lokalne",
    "cloud-api": "API w chmurze",
    "integrator-catalog": "Katalog integratora",
  },
  modelRole: {
    label: "Rola",
    "llm-engine": "Silnik LLM",
    "intent-embedding": "Embedding intencji",
  },
  trainability: {
    label: "Trenowalność",
    trainable: "Treniwalny",
    "not-trainable": "Nietreniwalny",
    badge: {
      trainable: "Treniwalny",
      notTrainable: "Nietreniwalny",
    },
    reasons: {
      notInCatalog: "Model nie znajduje się w katalogu trenowalnych modeli Academy",
      notAvailable: "Informacje o trenowalności niedostępne",
      cloudOnly: "Modele API w chmurze nie mogą być trenowane lokalnie",
    },
  },
}
```

### German (de)
```typescript
domain: {
  sourceType: {
    label: "Quelltyp",
    "local-runtime": "Lokale Laufzeit",
    "cloud-api": "Cloud-API",
    "integrator-catalog": "Integrator-Katalog",
  },
  modelRole: {
    label: "Rolle",
    "llm-engine": "LLM-Engine",
    "intent-embedding": "Intent-Embedding",
  },
  trainability: {
    label: "Trainierbarkeit",
    trainable: "Trainierbar",
    "not-trainable": "Nicht trainierbar",
    badge: {
      trainable: "Trainierbar",
      notTrainable: "Nicht trainierbar",
    },
    reasons: {
      notInCatalog: "Modell ist nicht im Academy-Katalog trainierbarer Modelle",
      notAvailable: "Informationen zur Trainierbarkeit nicht verfügbar",
      cloudOnly: "Cloud-API-Modelle können nicht lokal trainiert werden",
    },
  },
}
```

## Data Flow

```
User visits Models page
        ↓
useModelsViewerLogic hook loads
        ↓
useTrainableModels fetches /api/v1/academy/models/trainable
        ↓
        ├─ Cache hit (< 5 min) → Use cached data
        └─ Cache miss → Fetch from API → Store in localStorage
        ↓
Catalog models fetched from /api/v1/models/providers
        ↓
For each model card rendered:
        ↓
enrichCatalogModel(model, trainableModels)
        ↓
        ├─ inferSourceType(provider, runtime)
        ├─ inferModelRole(modelName, tags)
        └─ inferTrainability(modelName, trainableModels)
        ↓
EnrichedCatalogCard renders with domain badges
        ↓
User sees:
- Source Type badge (blue/purple/amber)
- Model Role badge (emerald/cyan)
- Trainability badge (green/gray) with tooltip
```

## Hover Interactions

### Trainability Badge Tooltip
When hovering over a "Not Trainable" badge:

```
┌──────────────────────────────────────────┐
│ [Not Trainable]                         │
│                                          │
│  ⓘ Model not in Academy trainable       │
│    catalog                               │
└──────────────────────────────────────────┘
```

or

```
┌──────────────────────────────────────────┐
│ [Not Trainable]                         │
│                                          │
│  ⓘ Cloud API models cannot be trained   │
│    locally                               │
└──────────────────────────────────────────┘
```

## Page Sections Where Badges Appear

1. **News Tab**
   - Trending Models (RECOMMENDED section)
   - Catalog (CATALOG section)

2. **Models Tab**
   - Search Results (FIND MODEL section)
   - Installed Models (future enhancement)

## Technical Implementation Notes

### Badge Component API

```typescript
<DomainBadges
  sourceType="integrator-catalog"
  sourceTypeLabel={t("models.domain.sourceType.integrator-catalog")}
  modelRole="llm-engine"
  modelRoleLabel={t("models.domain.modelRole.llm-engine")}
  trainabilityStatus="trainable"
  trainabilityLabel={t("models.domain.trainability.trainable")}
  trainabilityReason={null}
/>
```

### Individual Badge Components

```typescript
<SourceTypeBadge
  sourceType="cloud-api"
  label="Cloud API"
/>

<ModelRoleBadge
  role="intent-embedding"
  label="Intent Embedding"
/>

<TrainabilityBadge
  status="not-trainable"
  label="Not Trainable"
  reason="Cloud API models cannot be trained locally"
  showTooltip={true}
/>
```

## Cache Strategy

Trainable models are cached in localStorage with the key `trainable-models-cache`:

```json
{
  "data": [
    {
      "model_id": "llama-2-7b",
      "label": "Llama 2 7B",
      "provider": "huggingface",
      "trainable": true,
      "recommended": true
    }
  ],
  "timestamp": 1707901507000
}
```

Cache expires after 5 minutes (300,000 ms).

## Testing

All model domain mapper functions are tested:

```bash
npm run test:unit
# Runs tests/model-domain-mapper.test.ts
# 20 tests covering:
# - inferSourceType (7 tests)
# - inferModelRole (4 tests)
# - inferTrainability (6 tests)
# - enrichCatalogModel (2 tests)
# - enrichInstalledModel (1 test)
```

All tests pass with 100% coverage of the mapper logic.
