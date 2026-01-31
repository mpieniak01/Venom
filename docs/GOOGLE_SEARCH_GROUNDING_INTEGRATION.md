# Google Search Grounding Integration - Documentation

## Overview

Google Search Grounding integration allows the Venom Agent to access up‑to‑date information (news, markets, documentation), reducing hallucinations by using the native "Grounding with Google Search" mechanism in Gemini 1.5 models.

**Key features:**
- ✅ Native integration with Google Gemini 1.5 Pro
- ✅ Tied to Global Cost Guard (paid_mode)
- ✅ Automatic source citations
- ✅ Visual quality badges in UI
- ✅ DuckDuckGo fallback when paid mode is disabled

## Architecture

### 1. Backend: StateManager - Global Cost Guard

```python
from venom_core.core.state_manager import StateManager

# Init
state_manager = StateManager()

# Enable paid mode (Google Grounding available)
state_manager.set_paid_mode(True)

# Check status
if state_manager.is_paid_mode_enabled():
    print("Paid features enabled - Google Grounding available")
```

### 2. Backend: TaskType.RESEARCH

```python
from venom_core.execution.model_router import TaskType

# New research task type
task_type = TaskType.RESEARCH
```

### 3. Backend: Model Router

Router decides whether to use Google Grounding or DuckDuckGo:

```python
from venom_core.execution.model_router import HybridModelRouter, TaskType

router = HybridModelRouter()

# Research task - router picks backend
routing = router.route_task(TaskType.RESEARCH, "Current Bitcoin price")

# Depending on config:
# - paid_mode ON + Google API key -> Google Grounding
# - paid_mode OFF or missing API key -> DuckDuckGo (WebSearchSkill)
```

Decision logs:
```
[Router] Research mode: GROUNDING (Paid)  # paid_mode=True
[Router] Research mode: DUCKDUCKGO (Free) # paid_mode=False
```

### 4. Backend: Kernel Builder

```python
from venom_core.execution.kernel_builder import KernelBuilder

builder = KernelBuilder()

# enable_grounding controls Google Search
kernel = builder._register_service(
    kernel,
    service_type="google",
    model_name="gemini-1.5-pro",
    enable_grounding=True  # Enable Google Search Grounding
)
```

Google Search config (if the library is available):
```python
import google.generativeai as genai

genai.configure(api_key=GOOGLE_API_KEY)

# Enable grounding
tools = [{"google_search": {}}]
model = genai.GenerativeModel(
    model_name="gemini-1.5-pro",
    tools=tools
)
```

### 5. Backend: ResearcherAgent

Agent formats sources from Google Grounding automatically:

```python
from venom_core.agents.researcher import ResearcherAgent, format_grounding_sources

agent = ResearcherAgent(kernel)

# Process research query
result = await agent.process("What is the current Bitcoin price?")

# Response includes a sources section:
"""
Bitcoin currently costs around $43,500 according to latest data [1].

---
📚 Sources (Google Grounding):
[1] CoinMarketCap - Bitcoin Price - https://coinmarketcap.com/currencies/bitcoin/
[2] Bloomberg - Crypto Markets - https://bloomberg.com/crypto
"""

# Check search source
source = agent.get_last_search_source()
# 'google_grounding' or 'duckduckgo'
```

### 6. Frontend: UI Badges

Visual data source badges in UI:

```javascript
// Badge 🌍 Google Grounded (blue)
// - shown when Google Search Grounding is used
// - color: #1e40af

// Badge 🦆 Web Search (gray)
// - shown when DuckDuckGo is used
// - color: #6b7280
```

## Usage Scenarios

### Scenario 1: Paid Mode OFF (default)

```python
# Initial state
state_manager.set_paid_mode(False)

# User asks: "Current Bitcoin price?"
# ↓
# Router: TaskType.RESEARCH → LOCAL + DuckDuckGo
# ↓
# ResearcherAgent uses WebSearchSkill (DuckDuckGo)
# ↓
# Response with badge 🦆 Web Search
```

**Logs:**
```
[Router] Research mode: DUCKDUCKGO (Free)
[WebSearchSkill] Searching 'current bitcoin price'...
[ResearcherAgent] Used DuckDuckGo
```

### Scenario 2: Paid Mode ON

```python
# Enable paid mode
state_manager.set_paid_mode(True)

# User asks: "Current Bitcoin price?"
# ↓
# Router: TaskType.RESEARCH → CLOUD + Google Grounding
# ↓
# KernelBuilder: enable_grounding=True
# ↓
# Google Gemini with Google Search Grounding
# ↓
# Response with badge 🌍 Google Grounded + citations
```

**Logs:**
```
[Router] Research mode: GROUNDING (Paid)
[KernelBuilder] Google Gemini config: model=gemini-1.5-pro, grounding=True
[ResearcherAgent] Added Google Grounding sources to response
```

### Scenario 3: Fallback (missing API key)

```python
# Paid mode enabled, but no Google API key
state_manager.set_paid_mode(True)
# GOOGLE_API_KEY = ""

# ↓
# Router: TaskType.RESEARCH → LOCAL (fallback)
# ↓
# DuckDuckGo despite paid_mode
# ↓
# Badge 🦆 Web Search
```

**Logs:**
```
[Router] Research mode: RESEARCH -> LOCAL (DuckDuckGo fallback)
```

## Acceptance Criteria (DoD)

✅ **1. Paid Mode OFF → DuckDuckGo**
```python
state_manager.set_paid_mode(False)
# Agent uses DuckDuckGo
# Logs: "[Router] Research mode: DUCKDUCKGO (Free)"
# UI: Badge 🦆 Web Search
```

✅ **2. Paid Mode ON → Google Grounding**
```python
state_manager.set_paid_mode(True)
# Agent uses Google Grounding
# Logs: "[Router] Research mode: GROUNDING (Paid)"
# UI: Badge 🌍 Google Grounded
# Response contains "📚 Sources (Google Grounding)"
```

✅ **3. Formatting grounding_metadata**
```python
response_metadata = {
    "grounding_metadata": {
        "grounding_chunks": [
            {"title": "Bitcoin Price", "uri": "https://example.com"}
        ]
    }
}

sources = format_grounding_sources(response_metadata)
# Returns formatted sources section
```

✅ **4. Cost guard**
```python
# Attempt to force Google Search when paid_mode=False
# → System automatically uses DuckDuckGo
# → Guard cannot be bypassed
```

## Configuration

### Environment variables

```bash
# .env
GOOGLE_API_KEY=your-google-api-key-here
AI_MODE=HYBRID
HYBRID_CLOUD_PROVIDER=google
HYBRID_CLOUD_MODEL=gemini-1.5-pro
```

### Enable/disable paid mode

#### Via API:
```python
POST /api/v1/settings/paid-mode
{
  "enabled": true
}
```

#### Programmatically:
```python
from venom_core.core.state_manager import StateManager

state_manager = StateManager()
state_manager.set_paid_mode(True)
```

## Security

### Global Cost Guard

- ✅ Paid mode disabled by default (`paid_mode_enabled=False`)
- ✅ State persisted in `state_dump.json`
- ✅ No bypass - router enforces fallback
- ✅ All routing decisions logged

### Limits

- Google Search Grounding works only with `gemini-1.5-pro`
- Requires a valid Google API key
- Google Search costs are billed separately by Google

## Troubleshooting

### Problem: Google Grounding does not work even with paid_mode=True

**Check:**
1. Is `GOOGLE_API_KEY` set?
2. Is the model `gemini-1.5-pro`?
3. Is `google-generativeai` installed?

```bash
pip install google-generativeai
```

### Problem: No citations in response

**Causes:**
- Model did not use Google Search (query didn’t need fresh data)
- Missing `grounding_metadata` in response
- ResearcherAgent used DuckDuckGo (paid_mode=False)

**Check logs:**
```
[ResearcherAgent] Added Google Grounding sources to response  # OK
[ResearcherAgent] Used DuckDuckGo  # Fallback
```

### Problem: Badge not shown in UI

**Check:**
- Does metadata include `search_source`?
- Does WebSocket pass `eventData`?
- Is CSS for `.research-source-badge` loaded?

## Roadmap

### Phase 1: Infrastructure ✅ (Current)
- [x] StateManager: paid_mode_enabled
- [x] TaskType.RESEARCH
- [x] Router: decision logic
- [x] KernelBuilder: enable_grounding
- [x] ResearcherAgent: source formatting
- [x] Frontend: UI badges

### Phase 2: Full Integration (TODO)
- [ ] Implement dedicated Google Gemini connector for Semantic Kernel
- [ ] WebSocket events with metadata (search_source)
- [ ] API endpoint for paid_mode toggle
- [ ] Google Search cost monitoring

### Phase 3: Optimization (TODO)
- [ ] Google Search result cache
- [ ] Rate limiting for Google API
- [ ] Usage statistics (Google vs DuckDuckGo)
- [ ] A/B testing response quality

## See also

- [Google AI - Grounding with Google Search](https://ai.google.dev/docs/grounding)
- [Semantic Kernel Documentation](https://learn.microsoft.com/en-us/semantic-kernel/)
- [DuckDuckGo Search API](https://duckduckgo.com/api)
