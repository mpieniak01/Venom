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
- `models_remote.py` - /models/remote/providers, /models/remote/catalog, /models/remote/connectivity, /models/remote/validate
- `models_translation.py` - /translate

## Runtime i routing modeli
- `venom_core/execution/model_router.py` i `venom_core/core/model_router.py` – routing pomiedzy lokalnym LLM i chmura (LOCAL/HYBRID/CLOUD).
- `venom_core/core/llm_server_controller.py` – kontrola serwerow LLM (Ollama/vLLM/ONNX) i healthcheck.
- `venom_core/core/generation_params_adapter.py` – mapowanie parametrow generacji na format OpenAI/vLLM/Ollama/ONNX.
- Konfiguracja runtime znajduje sie w `venom_core/config.py` oraz `.env` (np. `LLM_LOCAL_ENDPOINT`, `VLLM_ENDPOINT`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`).

### Ujednolicony kontrakt opcji runtime (PR 185)
- `GET /api/v1/system/llm-runtime/options` jest kanonicznym kontraktem UI dla selektorow runtime/model.
- Odpowiedz zawiera:
  - snapshot aktywnego runtime (`active_server`, `active_model`, `config_hash`, `source_type`),
  - cele runtime local + cloud (`ollama`, `vllm`, `onnx`, `openai`, `google`),
  - listy modeli zgrupowane per runtime target.
- `POST /api/v1/system/llm-runtime/active` waliduje parę provider/model dla cloud runtime:
  - model musi należeć do katalogu wybranego providera,
  - niepoprawna para zwraca `400` z czytelnym komunikatem.
- `GET /api/v1/system/llm-servers` pozostaje endpointem technicznym dla runtime lokalnych; flow operacyjne UI (Chat + Models) używają `llm-runtime/options`.

### Rozwiazywanie aliasu feedback-loop (PR 187)
- Alias produktowy dla coding feedback-loop:
  - `requested_alias`: `OpenCodeInterpreter-Qwen2.5-7B`
  - `primary`: `qwen2.5-coder:7b`
  - `fallbacks`: `qwen2.5-coder:3b`, `codestral:latest`
- Runtime options (`GET /api/v1/system/llm-runtime/options`) zwraca teraz:
  - pola resolution aktywnego runtime: `requested_model_alias`, `resolved_model_id`, `resolution_reason`,
  - metadata per model: `feedback_loop_ready`, `feedback_loop_tier`,
  - blok statusu feedback-loop z `requested_alias`, `primary`, `fallbacks`.
- Aktywacja runtime lokalnego (`POST /api/v1/system/llm-servers/active`) obsluguje:
  - opcjonalne `model_alias` i `exact_only`,
  - jawny payload resolution (`requested_model_alias`, `resolved_model_id`, `resolution_reason`),
  - guard zasobowy dla 7B z bezpiecznym fallbackiem (lub blad gdy `exact_only=true`).
- Instalacja modeli (`POST /api/v1/models/install`) obsluguje alias feedback-loop:
  - idempotencja (brak ponownego pull przy juz zainstalowanym modelu),
  - retry + timeout dla `ollama pull`,
  - plan kandydatow zalezny od guardow (`primary` lub fallback chain).

### Ujednolicony kontrakt katalogu modeli (PR 191C)
- Kanoniczny kontrakt selektorów runtime/model: `GET /api/v1/system/llm-runtime/options`.
- `model_catalog.trainable_models` zawiera:
  - miejsce wykonywania treningu: `source_type` (`local` | `cloud`),
  - klasyfikacje kosztu: `cost_tier` (`free` | `paid` | `unknown`),
  - stabilny klucz kolejnosci backendu: `priority_bucket`,
  - mape kompatybilnosci inferencyjnej: `runtime_compatibility` (`{ [runtime_id]: boolean }`),
  - opcjonalny runtime rekomendowany: `recommended_runtime`.
- Kolejnosc jest autorytatywna po stronie backendu (frontend tylko ja renderuje):
  - `local + installed_local` -> `local` -> `cloud free` -> `cloud unknown` -> `cloud paid`.
- Kompatybilnosc runtime ma wynikac z realnie dostepnego lokalnego stosu/katalogu, a nie z hardkodowanych kluczy runtime.
- Aktywacja adaptera (`POST /api/v1/academy/adapters/activate`) waliduje kompatybilnosc:
  - opcjonalny parametr `runtime_id`,
  - przy niekompatybilnym `base_model + adapter + runtime` zwraca `400`.

### Docelowy kontrakt Academy (PR 196)
Academy, Samodoskonalenie, Adaptery i Chat muszą realizować jeden jawny proces:

1. Użytkownik wybiera `server/runtime`.
2. Użytkownik wybiera model runtime.
3. Użytkownik wybiera jawny `base_model` z `model_catalog.trainable_models`.
4. Academy wytwarza adapter z kanonicznym `metadata.json`.
5. Adapter może być aktywowany tylko dla jawnego `runtime_id + model_id`.

Twarde zasady:

- `GET /api/v1/system/llm-runtime/options` jest jedynym źródłem prawdy dla selektorów runtime/model w Chat, Training i Self-learning.
- Routery `venom_core/api/routes/academy*.py` pozostają cienką warstwą HTTP; orkiestracja należy do `venom_core/services/academy/*`.
- Deploy, audit i aktywacja adaptera ufają wyłącznie kanonicznym metadanym adaptera, a nie heurystykom z `adapter_config.json`, `runs.jsonl` ani domyślnym wartościom z konfiguracji.
- Academy nie może fallbackować semantycznie do `ACADEMY_DEFAULT_BASE_MODEL`, `LAST_MODEL_*` ani `LLM_MODEL_NAME` przy wyborze modelu bazowego treningu, modelu runtime ani celu aktywacji adaptera.
- Historyczne adaptery bez kanonicznego `metadata.json` są nieważnymi artefaktami; należy je usunąć albo wygenerować ponownie, a nie naprawiać ręcznie.
- Błędy user-facing w Academy powinny używać structured payloadów z `reason_code` i kontekstem requestu, a nie ad-hoc stringów.

Implikacje repo:

- Jeśli nowa trasa Academy potrzebuje logiki operacyjnej, należy dodać lub rozszerzyć service w `venom_core/services/academy/*`, zamiast importować niższe warstwy bezpośrednio do routera.
- Jeśli testy utrwalają fallback do domyślnego modelu w Academy, należy je przepisać na regresje dla jawnego kontraktu procesu, a nie utrzymywać jako kompatybilność wsteczną.

## Warstwa Wykonawcza (Skills & MCP)
Zintegrowana z Microsoft Semantic Kernel, pozwala na rozszerzanie możliwości agentów:
- `venom_core/execution/skills/base_skill.py` – Klasa bazowa dla wszystkich umiejętności.
- `venom_core/skills/mcp_manager_skill.py` – Zarządzanie narzędziami MCP (import z Git, venv).
- `venom_core/skills/mcp/proxy_generator.py` – Automatyczne generowanie kodu proxy dla serwerów MCP.
- `venom_core/skills/custom/` – Katalog umiejętności generowanych runtime (może nie istnieć na świeżym checkout do pierwszego importu MCP).

## Powiązana dokumentacja (MCP)
- `docs/PL/DEV_GUIDE_SKILLS.md` – import MCP i standardy Skills.
- `docs/PL/TREE.md` – struktura repo i katalogi MCP.

## Kontrakty API
Sciezki endpointow pozostaly bez zmian. Refaktor dotyczy tylko struktury kodu.

## Chat routing (uwaga spójności)
Tryby czatu (Direct/Normal/Complex) oraz zasady routingu/intencji są opisane w `docs/PL/CHAT_SESSION.md`.

## Optymalizacje Wydajności (v2026-02)
### Fast Path (Szablony)
- **Logika**: Statyczne intencje (`HELP_REQUEST`, `TIME_REQUEST`, `INFRA_STATUS`) pomijają budowanie ciężkiego kontekstu (pamięć/historia) dla latencji poniżej 100ms.
- **Trasa**: `Orchestrator._run_task_fastpath`.
- **Standaryzacja UTC**: Wszystkie wewnętrzne znaczniki czasu są wymuszane do UTC w `tracer.py` i `models.py`, co zapewnia spójność między usługami i poprawne etykiety "czasu relatywnego" w UI.

### Przetwarzanie w Tle (Background Processing)
- **ResultProcessor**: Niekrytyczne operacje (zapis do Vector Store, logi RL) są przenoszone do zadań w tle (`asyncio.create_task`), aby odblokować UI.
### Backend IO / Storage
- **Debouncing**: `StateManager`, `RequestTracer` i `SessionStore` używają mechanizmu debounce dla operacji zapisu na dysk, minimalizując I/O.
- **Trwałość Sesji**: `SessionStore` zachowuje historię czatu po restartach backendu poprzez aktualizację `boot_id` zamiast czyszczenia sesji.
- **Optymalizacja Ollama**: Dodano ustawienie `LLM_KEEP_ALIVE`, aby zapobiec wyładowywaniu modelu, co znacząco skraca TTFT w trybie Direct.
- **Czyste Zatrzymanie**: Polecenie `make stop` jawnie wyładowuje modele z VRAM za pomocą `keep_alive: 0`, przywracając system do stanu idealnego.
