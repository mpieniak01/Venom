# Przewodnik po Profilach Runtime Venom

## Przegląd

Venom wspiera trzy różne profile runtime, aby dostosować się do różnych wymagań sprzętowych, prywatności i operacyjnych. Każdy profil ma jawnie zdefiniowane możliwości i ograniczenia w kodzie.

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
- ❌ Brak lokalnego LLM (Ollama/vLLM wyłączone)
- ❌ Brak wymagania GPU
- ❌ Brak wymagania ONNX

**Uruchomione Usługi:**
- `backend` - Główny serwer API
- `frontend` - UI Next.js

**Wyłączone Usługi:**
- `ollama` - Zatrzymane/nie uruchomione
- `vllm` - Zatrzymane/nie uruchomione

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
- Może używać Ollama lub vLLM

**Możliwości:**
- ✅ Usługi Backend + Frontend
- ✅ Lokalny LLM (domyślnie Ollama, opcjonalnie vLLM)
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

---

## Używanie Profili

### Interaktywny Onboarding

```bash
./scripts/docker/venom.sh
```

Launcher zapyta Cię o:
1. Wybór języka (English/Polski/Deutsch)
2. Wybór profilu (LIGHT/API/FULL)
3. Wybór akcji (Start/Install/Reinstall/Uninstall/Status)

### Tryb Nieinteraktywny

```bash
# Start profilu LIGHT z angielskim
./scripts/docker/venom.sh --quick --lang en --profile light --action start

# Start profilu API z polskim
./scripts/docker/venom.sh --quick --lang pl --profile api --action start

# Sprawdzenie statusu dla profilu FULL
./scripts/docker/venom.sh --quick --lang de --profile full --action status
```

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

### Core-Light (Domyślny dla light/llm_off)

Instalacja:
```bash
pip install -r requirements-docker-minimal.txt
```

Zawiera:
- FastAPI, Uvicorn, Pydantic
- Główne narzędzia (httpx, aiofiles, loguru)
- Semantic Kernel, Redis, WebSockets
- BEZ ONNX, BEZ ciężkich zależności ML

### Extras-ONNX (Opcjonalne dla full)

Instalacja:
```bash
pip install -r requirements-extras-onnx.txt
```

Zawiera:
- ONNX Runtime (GPU lub CPU)
- Optimum, Accelerate
- Faster Whisper, Piper TTS

### Pełny Stack

Instalacja:
```bash
pip install -r requirements.txt
```

Zawiera wszystko (core-light + extras-onnx + narzędzia deweloperskie).

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
2. Ręcznie zainstaluj extras: `pip install -r requirements-extras-onnx.txt`

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
