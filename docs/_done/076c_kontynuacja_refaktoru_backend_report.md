# 76c: Kontynuacja refaktoru backendu - raport

## Cel i zakres
- Domkniecie refaktoru backendu w obszarach routes/models oraz model_registry.
- Uporzadkowanie zaleznosci i wydzielenie adapterow I/O.

## Zrealizowane refaktory

### 1) Podzial routes/models na sub-routery
- Utworzono moduly:
  - `venom_core/api/routes/models_install.py`
  - `venom_core/api/routes/models_usage.py`
  - `venom_core/api/routes/models_registry.py`
  - `venom_core/api/routes/models_registry_ops.py`
  - `venom_core/api/routes/models_config.py`
  - `venom_core/api/routes/models_translation.py`
- Dodano wspolne zaleznosci i helpery:
  - `venom_core/api/routes/models_dependencies.py`
  - `venom_core/api/routes/models_utils.py`
- `venom_core/api/routes/models.py` pelni role agregatora (bez logiki endpointow).

### 2) Wydzielenie adapterow I/O z ModelRegistry
- Dodano `venom_core/core/model_registry_clients.py`:
  - `OllamaClient` (HTTP + CLI)
  - `HuggingFaceClient` (HTTP + snapshot download)
- `ModelRegistry` korzysta z klientow dla list, newsow i operacji zewnetrznych.
- Providery `OllamaModelProvider` i `HuggingFaceModelProvider` uzywaja klientow zamiast bezposredniego I/O.

### 3) Doprecyzowanie granic ModelManager vs ModelRegistry
- Dodano dokument: `docs/BACKEND_ARCHITECTURE.md`.

## Zmiany w API/kontraktach
- Brak zmian w sciezkach endpointow ani payloadach.

## Wplyw na testy
- Zmiany strukturalne w routerach i ModelRegistry. Zalecane testy:
  - `pytest tests/test_*api*.py`
  - `pytest tests/test_model*.py`

## Zmiany w dokumentacji
- `docs/BACKEND_ARCHITECTURE.md`
