# Backend Architecture (Model Management)

## Zakres
Ten dokument opisuje podzial odpowiedzialnosci w obszarze zarzadzania modelami oraz strukture routerow API po refaktorze 76c.

## Podzial odpowiedzialnosci

### ModelRegistry (venom_core/core/model_registry.py)
- Discovery i katalog modeli (registry: providers/trending/news).
- Instalacja/usuwanie modeli przez providery.
- Metadane i capabilities modeli (manifest, schema generacji).
- Operacje asynchroniczne na modelach (ModelOperation).
- Nie wykonuje bezposrednio I/O - korzysta z adapterow (clients).

### ModelManager (venom_core/core/model_manager.py)
- Lifecycle i wersjonowanie modeli lokalnych.
- Resource guard (limity, metryki uzycia, odciazenia).
- Aktywacja wersji i operacje na modelach lokalnych.

## Adaptery I/O (clients)
- `venom_core/core/model_registry_clients.py`
  - `OllamaClient` - HTTP + CLI dla ollama (list_tags, pull, remove).
  - `HuggingFaceClient` - HTTP (list, news) + snapshot download.

## Routery API modeli
Routery zlozone sa w `venom_core/api/routes/models.py` (agregator). Submoduly:
- `models_install.py` - /models, /models/install, /models/switch, /models/{model_name}
- `models_usage.py` - /models/usage, /models/unload-all
- `models_registry.py` - /models/providers, /models/trending, /models/news
- `models_registry_ops.py` - /models/registry/install, /models/registry/{model_name}, /models/activate, /models/operations
- `models_config.py` - /models/{model_name}/capabilities, /models/{model_name}/config
- `models_translation.py` - /translate

## Kontrakty API
Sciezki endpointow pozostaly bez zmian. Refaktor dotyczy tylko struktury kodu.

## Chat routing (uwaga spójności)
Tryby czatu (Direct/Normal/Complex) oraz zasady routingu/intencji są opisane w `docs/CHAT_SESSION.md`.
