# Przewodnik po Profilach Runtime Venom

## Przegląd

Venom wspiera trzy różne profile runtime, aby dostosować się do różnych wymagań sprzętowych, prywatności i operacyjnych. Każdy profil ma jawnie zdefiniowane możliwości i ograniczenia w kodzie.

## Kanoniczne odnośniki

- Baseline benchmarków (3-stack): `docs/PL/LLM_RUNTIME_3STACK_BENCHMARK_BASELINE.md`
- Instalacja WSL i zasady pamięci: `docs/PL/WINDOWS_WSL_D_DRIVE_INSTALL.md`
- Monitoring operacyjny: `README_PL.md` (sekcja `Monitoring i higiena środowiska`)

Ten dokument jest źródłem prawdy dla wymagań profili i kontekstu środowiskowego. Wyniki pomiarów runtime utrzymujemy w baseline benchmarku.

## Kontrakt dostępności runtime (bez hardkodowania stosu)

Silniki runtime (`ollama`, `vllm`, `onnx`) to opcje konfiguracyjno-instalacyjne, a nie stały zestaw gwarantowany na każdym hoście.
W danym profilu/środowisku dostępny może być tylko podzbiór.

Kanoniczne wykrywanie runtime dla UI/automatyzacji:

- `GET /api/v1/system/llm-runtime/options`
  - zwraca snapshot aktywnego runtime i realnie dostępne targety runtime/modele,
  - jest źródłem prawdy dla selektorów runtime/model.

Kontrakt kompatybilności Academy (trening -> inferencja):

- `GET /api/v1/system/llm-runtime/options`
  - zwraca ujednolicony `model_catalog`, w tym `trainable_models`,
  - `trainable_models` zawiera `runtime_compatibility` i `recommended_runtime` wyliczane z realnie dostępnego lokalnego stosu,
  - `trainable_models` zawiera `source_type`, `cost_tier`, `priority_bucket` dla porządku local-first.
- `POST /api/v1/academy/adapters/activate`
  - przyjmuje opcjonalny `runtime_id`,
  - odrzuca niekompatybilne kombinacje `base_model + adapter + runtime` kodem `400`.

## Definicje Profili

### 1. Profil LIGHT (Privacy First)

**Opis:** lokalnie: Ollama + Gemma 3 + Next.js - Privacy First

**Zastosowanie:**
- Użytkownicy nastawieni na prywatność, którzy chcą lokalnego przetwarzania AI
- Środowiska ograniczone CPU/RAM
- Brak zależności od internetu dla głównych funkcji AI

**Możliwości:**
- ✅ Lokalny LLM (Ollama z Gemma 3)
- ✅ Usługi Backend + Frontend
- ✅ Opcjonalna akceleracja GPU
- ❌ Brak vLLM
- ❌ Brak wymagania ONNX (tylko zależności core-light)

**Uruchomione Usługi:**
- `backend` - Główny serwer API
- `frontend` - UI Next.js
- `ollama` - Lokalny serwer LLM

**Zmienne Środowiskowe:**
```bash
ACTIVE_LLM_SERVER=ollama
LLM_WARMUP_ON_STARTUP=true
OLLAMA_MODEL=gemma3:4b
```

**Wymagania Zasobów:**
- CPU: zalecane 4+ rdzenie
- RAM: zalecane 8GB+
- Dysk: 10GB+ dla modeli
- GPU: Opcjonalne, ale zalecane dla lepszej wydajności

---

### 2. Profil LLM_OFF (API/Cloud-Only)

**Opis:** cloud: OpenAI/Anthropic + Next.js - Low Hardware Req

**Zastosowanie:**
- Minimalne wymagania sprzętowe
- Przetwarzanie AI w chmurze/API
- Brak konieczności instalacji lokalnego LLM
- Model pay-per-use przez zewnętrznych dostawców

**Możliwości:**
- ✅ Usługi Backend + Frontend
- ✅ Zewnętrzni dostawcy API (OpenAI, Anthropic, Google/Gemini)
- ❌ Brak lokalnego LLM (Ollama/vLLM/ONNX wyłączone)
- ❌ Brak wymagania GPU
- ❌ Brak wymagania ONNX

**Uruchomione Usługi:**
- `backend` - Główny serwer API
- `frontend` - UI Next.js

**Wyłączone Usługi:**
- `ollama` - Zatrzymane/nie uruchomione
- `vllm` - Zatrzymane/nie uruchomione
- `onnx` - Runtime in-process wyłączony

**Zmienne Środowiskowe:**
```bash
ACTIVE_LLM_SERVER=none
LLM_WARMUP_ON_STARTUP=false
```

**Wymagane Klucze API (co najmniej jeden):**
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `GEMINI_API_KEY`

**Wymagania Zasobów:**
- CPU: 2+ rdzenie
- RAM: 4GB+
- Dysk: 5GB+ (brak modeli)
- GPU: Nie używane
- Internet: Wymagany do wywołań API

---

### 3. Profil FULL (The Beast)

**Opis:** rozszerzony stack - The Beast

**Zastosowanie:**
- Maksymalne możliwości
- Środowiska z GPU
- Zaawansowani użytkownicy, którzy chcą pełnej kontroli
- Może używać Ollama, vLLM lub ONNX

**Możliwości:**
- ✅ Usługi Backend + Frontend
- ✅ Lokalny stack LLM (domyślnie Ollama, vLLM/ONNX opcjonalnie i zależnie od środowiska)
- ✅ Wsparcie akceleracji GPU
- ✅ Opcjonalne extras ONNX
- ✅ Wszystkie zaawansowane funkcje włączone

**Uruchomione Usługi:**
- `backend` - Główny serwer API
- `frontend` - UI Next.js
- `ollama` - Lokalny serwer LLM (domyślnie)
- `vllm` - Opcjonalne (przez ACTIVE_LLM_SERVER=vllm)

**Zmienne Środowiskowe:**
```bash
ACTIVE_LLM_SERVER=ollama  # lub 'vllm' dla vLLM
LLM_WARMUP_ON_STARTUP=true
```

**Wymagania Zasobów:**
- CPU: zalecane 8+ rdzeni
- RAM: zalecane 16GB+
- Dysk: 20GB+
- GPU: Wysoce zalecane (NVIDIA ze wsparciem CUDA)

### Referencyjne środowisko benchmarkowe (2026-02-22)

To jest kontekst sprzętowo-systemowy użyty dla bieżącego baseline benchmarków LLM 3-stack:

- GPU: NVIDIA GeForce RTX 3060, 12 GB VRAM, CUDA 13.1
- CPU: Intel i5-14400F (16 wątków logicznych)
- RAM po stronie Linux runtime: ~15 GiB
- Kontekst hosta: Windows 32 GB RAM + WSL2

Uwaga WSL:
- W historycznych audytach środowiska `vmmem` potrafił utrzymywać wysoką rezerwację pamięci po skokach obciążenia.
- Limity i procedury restartu WSL utrzymuj zgodnie z `docs/PL/WINDOWS_WSL_D_DRIVE_INSTALL.md`.

### Zweryfikowany profil środowiska dla Academy ONNX E2E (2026-03-15)

Zweryfikowany profil dla pełnej ścieżki Academy ONNX (`merge_export -> activate -> inference -> deactivate`) na klasie hosta `32 GB RAM / 12 GB VRAM`:

- WSL2:
  - `memory=30GB`
  - `swap=16GB`
- Guard eksportu ONNX w Academy:
  - `ACADEMY_ADAPTER_MERGE_MAX_RSS_MB=23040`
- Runtime ONNX:
  - `ONNX_LLM_EXECUTION_PROVIDER=cuda`
  - `ONNX_LLM_PRECISION=int4`

Uwagi operacyjne:
- `merge_export` dla Gemma-3 jest RAM/CPU-heavy (peak RSS ~22-23 GB w tym profilu).
- Ten profil traktuj jako bazowy/rekomendowany dla direct deploy `Gemma-3 LoRA -> ONNX` w WSL2.

### Wskazówki dla profilu Ollama feedback-loop (PR 187)
- Docelowy alias klasy codingowej: `OpenCodeInterpreter-Qwen2.5-7B`.
- Polityka primary/fallback:
  - primary: `qwen2.5-coder:7b`
  - fallbacks: `qwen2.5-coder:3b`, `codestral:latest`
- Rekomendowane minimum zasobowe dla aktywacji 7B:
  - RAM: 12 GiB+
  - VRAM: 6 GiB+ (gdy metryki GPU są dostępne)
- Guard runtime/profilu:
  - `VENOM_OLLAMA_PROFILE=low-vram-8-12gb` wymusza fallback dla klasy 7B,
  - kontekst > `65536` jest traktowany jako niebezpieczny dla aktywacji 7B i zwraca błąd guard/fallback.
- Kanoniczne pola statusu dla UI/API:
  - `requested_model_alias`, `resolved_model_id`, `resolution_reason`
  - `feedback_loop_ready`, `feedback_loop_tier`
- Runbook operacyjny exact-vs-fallback:
  - `docs/PL/OLLAMA_FEEDBACK_LOOP_RUNBOOK.md`

---

## Używanie Profili

### Interaktywny Onboarding

```bash
./scripts/docker/venom.sh
```

Launcher zapyta Cię o:
1. Wybór języka (English/Polski/Deutsch)
2. Wybór profilu (LIGHT/API/FULL)
3. Wybór opcjonalnych dodatków (`vllm` i/lub `onnx` dla profilu ONNX LLM)
4. Wybór akcji (Start/Install/Reinstall/Uninstall/Status)

### Tryb Nieinteraktywny

```bash
# Start profilu LIGHT z angielskim
./scripts/docker/venom.sh --quick --lang en --profile light --action start

# Start profilu API z polskim
./scripts/docker/venom.sh --quick --lang pl --profile api --action start

# Start profilu FULL i instalacja dodatku ONNX LLM
./scripts/docker/venom.sh --quick --lang en --profile full --addons onnx --action install

# Sprawdzenie statusu dla profilu FULL
./scripts/docker/venom.sh --quick --lang de --profile full --action status
```

Uwaga do addonów:
- `--addons onnx` instaluje `requirements-profile-onnx.txt` (profil silnika ONNX LLM).
- `requirements-extras-onnx.txt` jest osobny i obecnie dodaje `faster-whisper` + `piper-tts`.

### Bezpośrednie Ustawienie Profilu

```bash
# Ustaw zmienną środowiskową profilu
export VENOM_RUNTIME_PROFILE=light

# Uruchom stack release
./scripts/docker/run-release.sh start
```

### Programowe Zastosowanie Profilu

```python
from venom_core.services.runtime_controller import runtime_controller

# Zastosuj profil
result = runtime_controller.apply_profile("light")
print(result)
# Wyjście zawiera:
# - success: bool
# - message: str
# - results: lista akcji usług
# - profile_capabilities: dict z uses_local_llm, gpu_support, requires_onnx
```

---

## Kontrakt Profilu

System profili jest wspierany przez formalny kontrakt w `venom_core/services/profile_config.py`:

```python
from venom_core.services.profile_config import (
    RuntimeProfile,
    get_profile_capabilities,
    get_profile_description,
    validate_profile_requirements,
)

# Pobierz możliwości
caps = get_profile_capabilities(RuntimeProfile.LIGHT)
print(caps.required_services)  # {'backend', 'frontend', 'ollama'}
print(caps.uses_local_llm)     # True
print(caps.requires_onnx)      # False

# Pobierz zlokalizowany opis
desc = get_profile_description(RuntimeProfile.LLM_OFF, lang="pl")
print(desc)  # "cloud: OpenAI/Anthropic + Next.js - Low Hardware Req"

# Waliduj wymagania
is_valid, error = validate_profile_requirements(
    RuntimeProfile.LLM_OFF,
    available_api_keys={"OPENAI_API_KEY"}
)
```

---

## Zależności według Profilu

### Bazowy profil API (domyślna instalacja)

Instalacja:
```bash
pip install -r requirements.txt
```

Zawiera:
- minimalny baseline API/cloud
- bez ciężkich lokalnych silników runtime w domyślnej instalacji (`vllm`/ONNX wyłączone)

### Core-Light (Docker/minimal runtime)

Instalacja:
```bash
pip install -r requirements-docker-minimal.txt
```

Zawiera:
- FastAPI, Uvicorn, Pydantic
- Główne narzędzia (httpx, aiofiles, loguru)
- Semantic Kernel, Redis, WebSockets
- BEZ ONNX, BEZ ciężkich zależności ML

### Profil ONNX LLM (trzeci silnik)

Instalacja:
```bash
pip install -r requirements-profile-onnx.txt
```

Zawiera:
- ONNX Runtime (GPU lub CPU)
- Optimum, Accelerate

### Extras-ONNX (opcjonalne dodatki)

Instalacja:
```bash
# Najpierw wybierz profil silnika ONNX:
# pip install -r requirements-profile-onnx.txt
# albo:
# pip install -r requirements-profile-onnx-cpu.txt
pip install -r requirements-extras-onnx.txt
```

Zawiera:
- Faster Whisper, Piper TTS

### Pełny Stack

Instalacja:
```bash
pip install -r requirements-full.txt
```

Zawiera pełny legacy zestaw (core + lokalne silniki + ciężkie extras + narzędzia deweloperskie).

### Full vs Profile (reguła operacyjna)

Domyślna ścieżka to `requirements.txt` + jeden wybrany profil.
`requirements-full.txt` używamy tylko na hostach specjalnych, które faktycznie wymagają legacy all-in stack.

Rekomendowany dobór:
- Typowy host dev/API/cloud: `requirements.txt`
- Lokalna inferencja ONNX (GPU): `requirements-profile-onnx.txt`
- Lokalna inferencja ONNX (CPU-only): `requirements-profile-onnx-cpu.txt`
- Lokalny runtime vLLM: `requirements-profile-vllm.txt`
- Opcjonalne dodatki voice/STT: `requirements-extras-onnx.txt` (po profilu ONNX/ONNX-CPU)
- Host legacy catch-all (jawny wyjątek): `requirements-full.txt`

### Instalacja per silnik runtime

```bash
# Instalacja pod Ollama (bez dodatkowych paczek Pythona względem API)
pip install -r requirements.txt

# Profil pod vLLM
pip install -r requirements-profile-vllm.txt

# Profil pod ONNX
pip install -r requirements-profile-onnx.txt

# Opcjonalne extras ONNX (audio/głos itd.)
# (instaluj po profilu ONNX/ONNX-CPU)
pip install -r requirements-extras-onnx.txt
```

---

## Migracja Profilu

Przełączanie między profilami jest bezpieczne i niedestrukcyjne:

```bash
# Przełącz z LIGHT na API
export VENOM_RUNTIME_PROFILE=llm_off
./scripts/docker/run-release.sh restart

# Przełącz z API na FULL
export VENOM_RUNTIME_PROFILE=full
./scripts/docker/run-release.sh restart
```

System:
1. Zatrzyma usługi niepotrzebne dla nowego profilu
2. Uruchomi usługi wymagane dla nowego profilu
3. Zastosuje odpowiednie nadpisania środowiskowe
4. Zachowa dane i konfigurację

---

## Rozwiązywanie Problemów

### Profil Nie Został Zastosowany

Sprawdź logi:
```bash
docker compose -f compose/compose.release.yml logs backend | grep -i profile
```

Zweryfikuj środowisko:
```bash
echo $VENOM_RUNTIME_PROFILE
```

### Profil API Bez Kluczy

Jeśli wybierzesz profil API bez skonfigurowanych kluczy API, launcher Cię ostrzeże. Skonfiguruj co najmniej jeden:

```bash
# W pliku .env lub export
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="..."
export GEMINI_API_KEY="..."
```

### ONNX Nie Znaleziono w Profilu Light

To zamierzone! Profil Light używa `requirements-docker-minimal.txt`, który wyklucza ONNX. Jeśli potrzebujesz funkcji ONNX:

1. Przełącz na profil FULL, lub
2. Zainstaluj profil ONNX LLM: `pip install -r requirements-profile-onnx.txt`
3. Opcjonalnie doinstaluj extras (po profilu ONNX/ONNX-CPU): `pip install -r requirements-extras-onnx.txt`

---

## Powiązana Dokumentacja

- [Podręcznik Operatora](../OPERATOR_MANUAL.md) - Administracja systemem
- [Przewodnik Docker Release](../DOCKER_RELEASE_GUIDE.md) - Procedury wdrożeniowe
- [Polityka Testowania](../TESTING_POLICY.md) - Profile testowania i CI

---

## Referencja API

### Enum Profilu

```python
class RuntimeProfile(str, Enum):
    LIGHT = "light"
    LLM_OFF = "llm_off"
    FULL = "full"
```

### Możliwości Profilu

```python
@dataclass(frozen=True)
class ProfileCapabilities:
    profile: RuntimeProfile
    required_services: Set[str]
    disabled_services: Set[str]
    env_overrides: Dict[str, str]
    required_api_keys: List[str]
    gpu_support: bool
    uses_local_llm: bool
    requires_onnx: bool
    description_en: str
    description_pl: str
    description_de: str
```

### Funkcje

- `get_profile_capabilities(profile: RuntimeProfile) -> ProfileCapabilities`
- `validate_profile_requirements(profile: RuntimeProfile, available_api_keys: Set[str]) -> tuple[bool, Optional[str]]`
- `get_profile_description(profile: RuntimeProfile, lang: str = "en") -> str`
