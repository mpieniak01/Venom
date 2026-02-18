# Venom Runtime Profiles Guide

## Overview

Venom supports three distinct runtime profiles to accommodate different hardware, privacy, and operational requirements. Each profile has explicit capabilities and constraints defined in the codebase.

## Profile Definitions

### 1. LIGHT Profile (Privacy First)

**Description:** Local Ollama + Gemma 3 + Next.js - Privacy First

**Use Case:** 
- Privacy-focused users who want local AI processing
- CPU/RAM limited environments
- No internet dependency for core AI features

**Capabilities:**
- ✅ Local LLM (Ollama with Gemma 3)
- ✅ Backend + Frontend services
- ✅ Optional GPU acceleration
- ❌ No vLLM
- ❌ No ONNX requirement (core-light dependencies only)

**Services Running:**
- `backend` - Core API server
- `frontend` - Next.js UI
- `ollama` - Local LLM server

**Environment Variables:**
```bash
ACTIVE_LLM_SERVER=ollama
LLM_WARMUP_ON_STARTUP=true
OLLAMA_MODEL=gemma3:4b
```

**Resource Requirements:**
- CPU: 4+ cores recommended
- RAM: 8GB+ recommended
- Disk: 10GB+ for models
- GPU: Optional, but recommended for better performance

---

### 2. LLM_OFF Profile (API/Cloud-Only)

**Description:** Cloud: OpenAI/Anthropic + Next.js - Low Hardware Req

**Use Case:**
- Minimal hardware requirements
- Cloud/API-based AI processing
- No local LLM installation needed
- Pay-per-use model via external providers

**Capabilities:**
- ✅ Backend + Frontend services
- ✅ External API providers (OpenAI, Anthropic, Google/Gemini)
- ❌ No local LLM (Ollama/vLLM disabled)
- ❌ No GPU requirement
- ❌ No ONNX requirement

**Services Running:**
- `backend` - Core API server
- `frontend` - Next.js UI

**Services Disabled:**
- `ollama` - Stopped/not started
- `vllm` - Stopped/not started

**Environment Variables:**
```bash
ACTIVE_LLM_SERVER=none
LLM_WARMUP_ON_STARTUP=false
```

**Required API Keys (at least one):**
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `GEMINI_API_KEY`

**Resource Requirements:**
- CPU: 2+ cores
- RAM: 4GB+
- Disk: 5GB+ (no models)
- GPU: Not used
- Internet: Required for API calls

---

### 3. FULL Profile (The Beast)

**Description:** Extended stack - The Beast

**Use Case:**
- Maximum capabilities
- GPU-enabled environments
- Advanced users who want full control
- Can use either Ollama or vLLM

**Capabilities:**
- ✅ Backend + Frontend services
- ✅ Local LLM (Ollama by default, vLLM optional)
- ✅ GPU acceleration support
- ✅ Optional ONNX extras
- ✅ All advanced features enabled

**Services Running:**
- `backend` - Core API server
- `frontend` - Next.js UI
- `ollama` - Local LLM server (default)
- `vllm` - Optional (via ACTIVE_LLM_SERVER=vllm)

**Environment Variables:**
```bash
ACTIVE_LLM_SERVER=ollama  # or 'vllm' for vLLM
LLM_WARMUP_ON_STARTUP=true
```

**Resource Requirements:**
- CPU: 8+ cores recommended
- RAM: 16GB+ recommended
- Disk: 20GB+
- GPU: Highly recommended (NVIDIA with CUDA support)

---

## Using Profiles

### Interactive Onboarding

```bash
./scripts/docker/venom.sh
```

The launcher will prompt you to:
1. Select language (English/Polski/Deutsch)
2. Select profile (LIGHT/API/FULL)
3. Select action (Start/Install/Reinstall/Uninstall/Status)

### Non-Interactive Mode

```bash
# Start LIGHT profile with English
./scripts/docker/venom.sh --quick --lang en --profile light --action start

# Start API profile with Polish
./scripts/docker/venom.sh --quick --lang pl --profile api --action start

# Status check for FULL profile
./scripts/docker/venom.sh --quick --lang de --profile full --action status
```

### Direct Profile Setting

```bash
# Set profile environment variable
export VENOM_RUNTIME_PROFILE=light

# Run release stack
./scripts/docker/run-release.sh start
```

### Programmatic Profile Application

```python
from venom_core.services.runtime_controller import runtime_controller

# Apply profile
result = runtime_controller.apply_profile("light")
print(result)  
# Output includes:
# - success: bool
# - message: str
# - results: list of service actions
# - profile_capabilities: dict with uses_local_llm, gpu_support, requires_onnx
```

---

## Profile Contract

The profile system is backed by a formal contract in `venom_core/services/profile_config.py`:

```python
from venom_core.services.profile_config import (
    RuntimeProfile,
    get_profile_capabilities,
    get_profile_description,
    validate_profile_requirements,
)

# Get capabilities
caps = get_profile_capabilities(RuntimeProfile.LIGHT)
print(caps.required_services)  # {'backend', 'frontend', 'ollama'}
print(caps.uses_local_llm)     # True
print(caps.requires_onnx)      # False

# Get localized description
desc = get_profile_description(RuntimeProfile.LLM_OFF, lang="pl")
print(desc)  # "cloud: OpenAI/Anthropic + Next.js - Low Hardware Req"

# Validate requirements
is_valid, error = validate_profile_requirements(
    RuntimeProfile.LLM_OFF, 
    available_api_keys={"OPENAI_API_KEY"}
)
```

---

## Dependencies by Profile

### Core-Light (Default for light/llm_off)

Install with:
```bash
pip install -r requirements-docker-minimal.txt
```

Includes:
- FastAPI, Uvicorn, Pydantic
- Core utilities (httpx, aiofiles, loguru)
- Semantic Kernel, Redis, WebSockets
- NO ONNX, NO heavy ML dependencies

### Extras-ONNX (Optional for full)

Install with:
```bash
pip install -r requirements-extras-onnx.txt
```

Includes:
- ONNX Runtime (GPU or CPU)
- Optimum, Accelerate
- Faster Whisper, Piper TTS

### Full Stack

Install with:
```bash
pip install -r requirements.txt
```

Includes everything (core-light + extras-onnx + development tools).

---

## Profile Migration

Switching between profiles is safe and non-destructive:

```bash
# Switch from LIGHT to API
export VENOM_RUNTIME_PROFILE=llm_off
./scripts/docker/run-release.sh restart

# Switch from API to FULL
export VENOM_RUNTIME_PROFILE=full
./scripts/docker/run-release.sh restart
```

The system will:
1. Stop services not needed for the new profile
2. Start services required for the new profile
3. Apply appropriate environment overrides
4. Preserve data and configuration

---

## Troubleshooting

### Profile Not Applied

Check logs:
```bash
docker compose -f compose/compose.release.yml logs backend | grep -i profile
```

Verify environment:
```bash
echo $VENOM_RUNTIME_PROFILE
```

### API Profile Without Keys

If you select the API profile without configuring API keys, the launcher will warn you. Configure at least one:

```bash
# In .env file or export
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="..."
export GEMINI_API_KEY="..."
```

### ONNX Not Found in Light Profile

By design! Light profile uses `requirements-docker-minimal.txt` which excludes ONNX. If you need ONNX features:

1. Switch to FULL profile, or
2. Manually install extras: `pip install -r requirements-extras-onnx.txt`

---

## Related Documentation

- [Operator Manual](OPERATOR_MANUAL.md) - System administration
- [Docker Release Guide](DOCKER_RELEASE_GUIDE.md) - Deployment procedures
- [Testing Policy](TESTING_POLICY.md) - Testing profiles and CI

---

## API Reference

### Profile Enum

```python
class RuntimeProfile(str, Enum):
    LIGHT = "light"
    LLM_OFF = "llm_off"
    FULL = "full"
```

### Profile Capabilities

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

### Functions

- `get_profile_capabilities(profile: RuntimeProfile) -> ProfileCapabilities`
- `validate_profile_requirements(profile: RuntimeProfile, available_api_keys: Set[str]) -> tuple[bool, Optional[str]]`
- `get_profile_description(profile: RuntimeProfile, lang: str = "en") -> str`
