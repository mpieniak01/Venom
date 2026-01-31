# Global Cost Guard - Documentation

## Overview

**Global Cost Guard** is a financial security mechanism in the Venom system that protects against uncontrolled API costs. The system defaults to **Eco (Local-Only)** mode, physically blocking access to paid APIs (OpenAI, Google Gemini). Users must consciously enable **Pro (Paid)** mode to gain access to cloud models.

## Features

### 1. Safety Reset (Safe Start)
- System **always** starts in Eco mode
- `paid_mode_enabled` state is **not persisted** to file
- Application restart resets mode to Eco
- Prevents accidentally leaving the "meter" running

### 2. Physical Gate (Cost Gate)
- Model Router checks `paid_mode_enabled` state before every cloud request
- If paid mode is disabled: automatic fallback to local model
- Logging of every blockage in system logs
- Zero leakage of requests to paid APIs

### 3. Transparency (Model Attribution)
- Every system response tagged with information about the model used
- Visual distinction: 🤖 for local, ⚡ for paid
- Badge on every message: green (free) / purple (paid)
- User sees in real-time what they're paying for

## Operation Modes

### Eco Mode (Default) 🌿
- **Status**: Local models only (Llama, Phi-3)
- **Cost**: $0.00
- **Icon**: Green badge
- **Behavior**: All requests directed to local LLM

### Pro Mode (Optional) 💸
- **Status**: Access to cloud models (GPT-4, Gemini)
- **Cost**: According to provider pricing
- **Icon**: Purple badge
- **Behavior**: Complex tasks directed to cloud (in HYBRID mode)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Venom Dashboard                         │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Header: [🌿 Eco Mode] ◄─► [💸 Pro Mode]            │    │
│  │          Toggle Switch + Modal Confirmation          │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    API: /api/v1/system/cost-mode            │
│  GET  → Retrieves current state (enabled: bool)            │
│  POST → Sets mode (enable: bool)                            │
└─────────────────────────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      StateManager                            │
│  • paid_mode_enabled: bool = False (ALWAYS at start)       │
│  • enable_paid_mode() → True                                │
│  • disable_paid_mode() → False                              │
│  • is_paid_mode_enabled() → bool                            │
└─────────────────────────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   HybridModelRouter                          │
│  ┌───────────────────────────────────────────────────┐      │
│  │ COST GUARD CHECK:                                 │      │
│  │  if target == "cloud" AND NOT paid_mode_enabled:  │      │
│  │      → FALLBACK TO LOCAL                          │      │
│  │      → LOG WARNING                                │      │
│  └───────────────────────────────────────────────────┘      │
│                                                              │
│  Routing Decision + Metadata:                               │
│  • target: "local" | "cloud"                                │
│  • model_name: "llama3" | "gpt-4o"                         │
│  • provider: "local" | "openai" | "google"                 │
│  • is_paid: bool                                            │
└─────────────────────────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  Response with Badge                         │
│  [Agent Message] [🤖 Llama 3] ← Free, Local                │
│  [Agent Message] [⚡ GPT-4o]  ← Paid, Cloud                 │
└─────────────────────────────────────────────────────────────┘
```

## Usage

### Dashboard UI

1. **Check current mode**:
   - Look at the toggle in the header
   - 🌿 Eco Mode = Free
   - 💸 Pro Mode = Paid

2. **Enable Pro Mode**:
   - Click the toggle
   - Confirm in dialog window
   - Read cost warning
   - Click "I Confirm and Accept Costs"

3. **Disable Pro Mode**:
   - Click the toggle
   - Automatic disable without confirmation

### Programmatic API

```python
import requests

# Check current mode
response = requests.get("http://localhost:8000/api/v1/system/cost-mode")
print(response.json())
# {"enabled": false, "provider": "hybrid"}

# Enable Pro Mode
response = requests.post(
    "http://localhost:8000/api/v1/system/cost-mode",
    json={"enable": True}
)
print(response.json())
# {"status": "success", "message": "Paid Mode (Pro) enabled...", "enabled": true}

# Disable Pro Mode
response = requests.post(
    "http://localhost:8000/api/v1/system/cost-mode",
    json={"enable": False}
)
```

### Backend (Python)

```python
from venom_core.core.state_manager import StateManager
from venom_core.execution.model_router import HybridModelRouter, TaskType

# Initialization
state_manager = StateManager()
router = HybridModelRouter(state_manager=state_manager)

# Default: Eco Mode (paid_mode_enabled = False)
routing = router.route_task(TaskType.CODING_COMPLEX, "Refactor code")
print(routing["target"])  # "local" - cloud access blocked
print(routing["is_paid"]) # False

# Enable Pro Mode
state_manager.enable_paid_mode()

# Now: cloud access available
routing = router.route_task(TaskType.CODING_COMPLEX, "Refactor code")
print(routing["target"])  # "cloud" - access to GPT-4/Gemini
print(routing["is_paid"]) # True
```

## Typical Usage Flow

### Scenario: Task requires cloud model

1. **User sends task**: "Analyze this architecture and propose refactoring"
2. **Router evaluates task**: TaskType.CODING_COMPLEX → normally cloud
3. **Cost Guard checks**: `paid_mode_enabled == False` → BLOCK
4. **Fallback to LOCAL**: Task executed by Llama 3
5. **UI shows badge**: [🤖 Llama 3 (Local)]
6. **User sees**: This was executed locally, zero costs

### Scenario: User enables Pro Mode

1. **Toggle click** → Modal with warning
2. **Confirmation** → POST /api/v1/system/cost-mode (enable: true)
3. **StateManager**: `paid_mode_enabled = True`
4. **Notification**: "💸 Pro Mode enabled - Cloud API available"
5. **Subsequent requests**: Can use GPT-4/Gemini (in HYBRID/CLOUD mode)
6. **UI Badge**: [⚡ GPT-4o] on cloud responses

## AI Mode Configuration

Global Cost Guard works with `AI_MODE` configuration:

### LOCAL Mode
```env
AI_MODE=LOCAL
```
- All tasks → local
- Cost Guard has no effect (cloud blocked anyway)

### HYBRID Mode (Recommended)
```env
AI_MODE=HYBRID
```
- Simple tasks → local (always)
- Complex tasks → cloud (only when `paid_mode_enabled == True`)
- Cost Guard active for complex tasks

### CLOUD Mode
```env
AI_MODE=CLOUD
```
- All tasks → cloud
- Cost Guard blocks ALL requests when `paid_mode_enabled == False`
- ⚠️ Note: In this mode disabled Cost Guard = no AI access

## Sensitive Data

**IMPORTANT**: Sensitive data **ALWAYS** goes to local model, regardless of:
- AI Mode (LOCAL/HYBRID/CLOUD)
- Cost Guard state (Eco/Pro)

```python
# Example: password in request
routing = router.route_task(
    TaskType.SENSITIVE,
    "Generate script with password: secret123"
)
print(routing["target"])  # "local" - ALWAYS
print(routing["reason"])  # "Sensitive data - HARD BLOCK..."
```

## Logs and Monitoring

### Logged Events

```
[WARNING] 🔒 COST GUARD: Blocked access to Cloud API. Fallback to LOCAL.
[WARNING] 🔓 Paid Mode ENABLED via API - user accepted costs
[INFO] 🔒 Paid Mode DISABLED via API - Eco mode active
```

### Token Metrics

Dashboard displays session cost:
```
Session Cost: $0.0000  (Eco Mode)
Session Cost: $0.0234  (Pro Mode - active GPT-4 usage)
```

## Security

### Built-in Safeguards

1. **Safety Reset**: Always start in Eco Mode
2. **No Persistence**: State not saved to disk
3. **Explicit Confirmation**: Modal when enabling Pro Mode
4. **Fallback Logic**: Error in Cost Guard → local (safe default)
5. **Sensitive Data Lock**: Sensitive data never to cloud

### Best Practices

1. **Disable Pro Mode after use**: Don't leave enabled overnight
2. **Monitor costs**: Regularly check "Session Cost"
3. **Use HYBRID**: Optimizes cost vs. quality
4. **Mark sensitive**: Use TaskType.SENSITIVE for personal data

## Troubleshooting

### Problem: Cannot get GPT-4 response

**Solution**:
1. Check if Pro Mode is enabled (toggle in header)
2. Check if you have `GOOGLE_API_KEY` or `OPENAI_API_KEY` set in `.env`
3. Check if `AI_MODE=HYBRID` or `CLOUD` in `.env`

### Problem: Cost Guard blocks despite Pro Mode enabled

**Solution**:
1. Check logs: `grep "COST GUARD" logs/venom.log`
2. Restart application: Pro Mode resets on restart
3. Enable again through UI

### Problem: Badge doesn't show on responses

**Solution**:
1. Ensure you're using latest frontend version
2. Check browser console: F12 → Console
3. Reload page: Ctrl+Shift+R (clear cache)

## Integration with Custom Code

If you're creating your own agent using HybridModelRouter:

```python
from venom_core.core.state_manager import StateManager
from venom_core.execution.model_router import HybridModelRouter

class MyCustomAgent:
    def __init__(self, state_manager: StateManager):
        # Pass state_manager to router
        self.router = HybridModelRouter(state_manager=state_manager)

    async def process_task(self, prompt: str):
        # Routing with Cost Guard
        routing = self.router.route_task(TaskType.STANDARD, prompt)

        # Use routing["model_name"], routing["provider"]
        # ...

        # Return response with metadata
        return {
            "response": "...",
            "metadata": {
                "model_name": routing["model_name"],
                "provider": routing["provider"],
                "is_paid": routing["is_paid"]
            }
        }
```

## FAQ

**Q: Does Cost Guard affect performance?**
A: No. Checking the `paid_mode_enabled` flag is O(1), practically zero overhead.

**Q: What if I forget to disable Pro Mode?**
A: Application restart automatically disables Pro Mode (Safety Reset).

**Q: Can I programmatically force Cloud API usage?**
A: No. Cost Guard is a physical gate - no bypass. You must enable Pro Mode.

**Q: How does it work in LOCAL mode?**
A: In LOCAL mode Cost Guard is transparent - cloud is blocked by AI_MODE anyway.

**Q: Does Cost Guard protect against all costs?**
A: Yes - blocks OpenAI, Google Gemini, Azure. Doesn't block local models (they're free).

## Changelog

### v1.4.0 (2024-12-09)
- ✨ Added Global Cost Guard
- ✨ Added Model Attribution (badges)
- ✨ Added Master Switch in UI
- ✨ Added API endpoints for cost mode
- ✨ Added Safety Reset mechanism
- 📝 Documentation COST_GUARD.md
- ✅ Unit tests for Cost Guard

## Contact

For questions or issues:
- GitHub Issues: [mpieniak01/Venom/issues](https://github.com/mpieniak01/Venom/issues)
- Documentation: `/docs/`

---

**Venom v1.4 - Global Cost Guard** 🛡️
*Zero Surprise Costs. Maximum Control.*
