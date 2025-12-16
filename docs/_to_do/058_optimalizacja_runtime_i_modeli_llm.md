# ZADANIE 058: Stabilizacja runtime LLM i automatyzacja zarządzania modelami

## Kontekst
- Obecnie utrzymujemy jednocześnie dwa lokalne runtime: **vLLM** (OpenAI-compatible) oraz **Ollama** (GGUF). Każdym sterujemy ręcznie przez wrappery bash (`scripts/llm/*`), a monitoring opiera się na okresowych pingach API.
- Serwery bywają restartowane zbyt często (manualne „przebijanie się” przez komendy i brak jasnych procedur). W efekcie widzimy „migający” status w panelu i możliwość powstawania zrzutów pamięci (niezamknięte procesy, zombie).
- Obecny ModelManager skupia się na katalogu `./models` i nie rozróżnia źródeł modeli (HF vs. Ollama). Instalacje/provisioning wykonujemy ręcznie, kopiując pliki lub wpisując `ollama pull`, co jest podatne na błędy i utrudnia zmianę modelu w locie.

## Cel
1. **Stabilny runtime** – serwery LLM działają jako deterministyczne procesy (systemd/supervisor), a panel pokazuje realny stan bez konieczności ciągłego odświeżania.
2. **Centralny menedżer modeli** – Venom potrafi samodzielnie pobierać, usuwać i przełączać modele zarówno z **Hugging Face** (dla vLLM) jak i z **Ollama Library** (GGUF).
3. **Operacje bez ręcznej interwencji** – operator z panelu wybiera model i runtime, a backend zajmuje się provisioningiem (download, walidacja, przełączenie).

## Problemy do rozwiązania
1. **Procesy** – brak gwarancji, że `stop` faktycznie ubija usługę (np. gdy Ollama działa jako systemd). Potrzebne rozróżnienie trybu „daemon systemowy” vs „process lokalny”.
2. **Zrzuty pamięci / zombie** – restart „na siłę” może zostawiać procesy `ollama serve` lub `python -m vllm.entrypoints.openai.api_server` z zajętą pamięcią GPU.
3. **Provisioning modeli HF** – obecnie sprowadza się do ręcznego kopiowania katalogów do `models/`. Brak cache, brak walidacji sum kontrolnych, brak metadanych (rozmiar, data, kompatybilność z GPU).
4. **Provisioning modeli Ollama** – brak API w panelu; użytkownik musi używać CLI. Nie mamy też listy dostępnych modeli (tylko to, co zwraca `/api/tags` lokalnej instancji).
5. **Przełączanie modeli** – zmiana `LLM_MODEL_NAME` wymaga restartu serwera i edycji `.env`. Potrzebny prosty workflow (np. `POST /api/v1/models/activate`), który:
   - Ubija bieżące zadania (lub czeka na idle),
   - Podmienia config,
   - Restartuje odpowiedni runtime,
   - Potwierdza w panelu nowy stan.

## Zakres wysokopoziomowy
1. **Runbook runtime**
   - Standard: vLLM i Ollama obsługiwane przez systemd (domyślny unit) + fallback do lokalnych skryptów.
   - Logowanie w `logs/{server}.log`, retencja + rotacja.
   - Health-check w ServiceMonitorze (status `online/degraded/offline`).
2. **Model Provisioning Service**
   - Backendowy moduł (`venom_core/core/model_registry.py`) z adapterami:
     - `HuggingFaceModelProvider` (używa `huggingface_hub`).
     - `OllamaModelProvider` (używa HTTP API + CLI fallback `ollama pull`).
   - Kolejka operacji (async) + raport postępu (SSE/powiadomienia).
3. **API do zarządzania modelami**
   - `GET /api/v1/models/providers` – lista available modeli (HF search, `ollama library list`).
   - `POST /api/v1/models/install` – `{"provider":"hf","model":"google/gemma-2b-it","runtime":"vllm"}`.
   - `POST /api/v1/models/remove` – usuwa z cache/OLLAMA.
   - `POST /api/v1/models/activate` – przełącza `LLM_MODEL_NAME` dla wskazanego runtime.
   - `GET /api/v1/models/operations` – statusy pobrań (progress, błędy).
4. **UI Cockpit**
   - Panel „Serwery LLM”: dodatkowa zakładka „Modele” per runtime (instalacja/usuwanie/aktywacja).
   - Progress bary i logi instalacji (np. streaming SSE).
   - Blokada akcji, gdy runtime jest w trakcie restartu/instalacji.
5. **Bezpieczeństwo i limity**
   - Konfiguracja `MODELS_MAX_DISK_GB`, `MODELS_CACHE_DIR`.
   - Walidacja, czy model jest kompatybilny (quantization, GPU vs CPU).
   - Idempotentne operacje (ponowienie pobierania dokończy przerwany download).

## Plan działania (propozycja)
1. **Analiza obecnych procesów**
   - Sprawdzić, czy vLLM/Ollama działają jako systemd service w docelowym środowisku (Linux). Przygotować unit `.service` (zawierający ExecStart, Restart=on-failure, LimitCORE=0 aby uniknąć zrzutów).
   - Zaktualizować `scripts/llm/*.sh`, by delegowały do systemd jeśli dostępny (częściowo wykonane dla Ollama – rozszerzyć o vLLM).
2. **Monitorowanie pamięci**
   - ServiceMonitor: nowe pola `memory_mb`, `uptime_seconds`.
   - Alert w panelu, gdy proces przekracza próg RAM/VRAM (np. >85%).
   - Dodać skrypt diagnostyczny `scripts/llm/debug_runtime.sh` (ps, lsof, tail logów).
3. **Hugging Face integration**
   - Wymagania: `HF_TOKEN` opcjonalnie, `huggingface_hub >= 0.23`.
   - Implementacja:
     - Klasa `HuggingFaceDownloader` (pobiera repo snapshot do `models_cache/hf/<model>@<revision>`).
     - Funkcja `prepare_for_vllm(model_id, dtype, quantization)` – sprawdza, czy model jest kompatybilny i ewentualnie przekonwertuje (np. `convert-hf-to-vllm`).
   - Metadata JSON (rozmiar, SHA256, friendly name) zapisywana w `models/manifest.json`.
4. **Ollama integration**
   - HTTP API `POST /api/pull` + `DELETE /api/delete`. Fallback CLI `ollama pull`.
   - Mechanizm liczenia postępu (API `POST /api/pull` zwraca stream logów → przekazać UI).
   - Endpoint `/api/v1/models/ollama/catalog` – caching listy z `https://registry.ollama.ai/library`.
5. **Model activation workflow**
   - `ModelManager` przechowuje mapę: runtime → aktywny model.
   - Aktywacja:
     1. Walidacja, czy model jest pobrany.
     2. Aktualizacja configu (np. `SETTINGS.LLM_MODEL_NAME` + dedicated `VLLM_ACTIVE_MODEL`).
     3. Restart runtime (systemd + health-check).
     4. Powiadomienie UI (`task_update` / SSE).
6. **UI**
   - Dwa panele: „vLLM Models”, „Ollama Models”.
   - Przyciski: Install, Activate, Remove. Tabela statusów (Installed / Downloading / Available remote).
   - Sekcja logów operacji (ostatnie 5).
7. **Testy**
   - Unit: `ModelRegistry` (download HF stub, progress).
   - Integration: `tests/test_model_install_api.py` – używa lokalnego HTTP serwera do udawania HF.
   - E2E: Playwright scenario instalacji i przełączenia modelu (mock backend).

## Ryzyka i otwarte pytania
1. **Wielkość modeli** – potrzebny limit (np. brak zgody na >20 GB bez potwierdzenia).
2. **GPU** – niektóre modele HF wymagają GPU. Czy przewidujemy fallback CPU? (Można dodać tag w manifestach).
3. **Równoległe operacje** – trzeba serializować instalacje per runtime, aby uniknąć wyścigów (np. `asyncio.Lock`).
4. **Ollama autorestart** – część użytkowników ma włączony autostart. Konieczne wykrycie i komunikaty, by nie dublować procesów.

## TODO (wysoki poziom)
- [ ] Przygotować definicje unitów systemd i zaktualizować skrypty startowe.
- [ ] Zaprojektować `ModelRegistry` + adaptery HF/Ollama.
- [ ] Dodać API do instalacji/usuwania/aktywacji modeli.
- [ ] Zmodernizować panel Cockpit (sekcja Modele + logi operacji).
- [ ] Testy jednostkowe + E2E pokrywające cały flow.

> Po akceptacji planu przygotujemy osobne PR-y: (1) runtime/systemd, (2) backend ModelRegistry + API, (3) UI + testy.
