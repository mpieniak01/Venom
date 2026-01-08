# THE SHADOW - Desktop Awareness & Proactive Assistance

## Overview

Shadow Agent is a proactive assistance system that monitors user activity (clipboard, active window) and offers contextual help without interrupting workflow. It's an intelligent "shadow" that observes your work and helps at key moments.

## Architecture

```
┌─────────────────┐
│ Desktop Sensor  │  ← Monitors clipboard and windows
└────────┬────────┘
         │ Sensor Data
         ↓
┌─────────────────┐
│  Shadow Agent   │  ← Analyzes context, generates suggestions
└────────┬────────┘
         │ Suggestions
         ↓
┌─────────────────┐
│    Notifier     │  ← Sends system notifications
└─────────────────┘
```

## Components

### 1. Desktop Sensor (`venom_core/perception/desktop_sensor.py`)

Monitors desktop activity:
- **Clipboard**: Detects clipboard changes (pyperclip)
- **Active Window**: Tracks active window title (Windows/Linux)
- **Screenshots**: Optionally takes screenshots (PIL)
- **Privacy Filter**: Blocks sensitive data (passwords, cards, API keys)

**Features:**
- Async monitoring loop with debouncing (1s)
- Automatic WSL2 detection
- Configurable max text length (default: 1000 chars)
- Thread-safe callbacks

**Usage Example:**
```python
from venom_core.perception.desktop_sensor import DesktopSensor

async def handle_clipboard(data):
    print(f"Clipboard changed: {data['content'][:50]}...")

sensor = DesktopSensor(
    clipboard_callback=handle_clipboard,
    privacy_filter=True
)
await sensor.start()
```

### 2. Shadow Agent (`venom_core/agents/shadow.py`)

Intelligent agent analyzing work context:
- **Error Detection**: Regex for tracebacks, exceptions
- **Code Analysis**: Heuristics for code snippets
- **Documentation Context**: Detects documentation reading
- **Learning**: Saves rejected suggestions to LessonsStore

**Suggestion Types:**
- `ERROR_FIX` - Fix code errors
- `CODE_IMPROVEMENT` - Improve code quality
- `TASK_UPDATE` - Update task status
- `CONTEXT_HELP` - Contextual help

**Usage Example:**
```python
from venom_core.agents.shadow import ShadowAgent

shadow = ShadowAgent(
    kernel=build_kernel(),
    confidence_threshold=0.8,
    lessons_store=lessons_store
)
await shadow.start()

suggestion = await shadow.analyze_sensor_data({
    "type": "clipboard",
    "content": "Traceback (most recent call last):\n  Error: ...",
    "timestamp": "2024-01-01T00:00:00"
})

if suggestion:
    print(f"Suggestion: {suggestion.title}")
    print(f"Confidence: {suggestion.confidence:.2%}")
```

### 3. Notifier (`venom_core/ui/notifier.py`)

Native notification system:
- **Windows**: Toast Notifications (win10toast + PowerShell fallback)
- **Linux**: notify-send (libnotify)
- **WSL2**: Bridge to Windows via powershell.exe

**Features:**
- Async subprocess execution
- Safe argument passing (no command injection)
- Support for notification actions
- Configurable urgency (low/normal/critical)

**Usage Example:**
```python
from venom_core.ui.notifier import Notifier

async def handle_action(payload):
    print(f"User clicked: {payload}")

notifier = Notifier(webhook_handler=handle_action)

await notifier.send_toast(
    title="Error detected",
    message="Found an error in your code",
    action_payload={"type": "error_fix", "code": "..."}
)
```

## Configuration

In `.env` file:

```env
# Enable Shadow Agent
ENABLE_PROACTIVE_MODE=True
ENABLE_DESKTOP_SENSOR=True

# Confidence threshold for suggestions (0.0-1.0)
SHADOW_CONFIDENCE_THRESHOLD=0.8

# Privacy filter
SHADOW_PRIVACY_FILTER=True

# Max clipboard text length
SHADOW_CLIPBOARD_MAX_LENGTH=1000

# Check interval (seconds)
SHADOW_CHECK_INTERVAL=1
```

## API Endpoints

### GET /api/v1/shadow/status
Returns Shadow Agent and component status.

**Response:**
```json
{
  "status": "success",
  "shadow": {
    "shadow_agent": {
      "is_running": true,
      "confidence_threshold": 0.8,
      "queued_suggestions": 0,
      "rejected_count": 2
    },
    "desktop_sensor": {
      "is_running": true,
      "system": "Linux",
      "is_wsl": false,
      "privacy_filter": true
    },
    "notifier": {
      "system": "Linux",
      "is_wsl": false,
      "webhook_handler_set": true
    },
    "config": {
      "confidence_threshold": 0.8,
      "privacy_filter": true,
      "desktop_sensor_enabled": true
    }
  }
}
```

### POST /api/v1/shadow/reject
Registers a rejected suggestion for learning.

**Body:**
```json
{
  "suggestion_type": "error_fix"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Rejected suggestion of type 'error_fix' registered"
}
```

## Privacy & Security

### Privacy Filter
Blocks the following data types:
- 💳 Credit card numbers (`\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}`)
- 📧 Email addresses (optional)
- 🔑 Passwords (`password:`, `hasło:`, `pwd:`)
- 🔐 API keys and tokens
- 🌐 IP addresses (optional)
- 🔒 Private keys (PEM format)

### Security Features
- ✅ No command injection (subprocess with argument list)
- ✅ Regex validation for sensitive data
- ✅ Configurable max text length
- ✅ CodeQL security check passed (0 alerts)

## Workflow - Example Scenario

1. **User copies error to clipboard:**
   ```python
   Traceback (most recent call last):
     File "main.py", line 10
       result = 10 / 0
   ZeroDivisionError: division by zero
   ```

2. **Desktop Sensor detects change:**
   - Privacy Filter checks for sensitive data
   - Passes to Shadow Agent

3. **Shadow Agent analyzes:**
   - Regex detects `ZeroDivisionError`
   - Generates `ERROR_FIX` suggestion
   - Confidence: 85% (> threshold 80%)

4. **Notifier sends notification:**
   ```
   ┌────────────────────────────────────┐
   │ 🔍 Venom                           │
   │                                    │
   │ Error detected in clipboard        │
   │ Found an error in copied code.     │
   │ Would you like me to analyze it?   │
   │                                    │
   │ [Analyze] [Reject]                 │
   └────────────────────────────────────┘
   ```

5. **User clicks [Reject]:**
   - Shadow Agent saves rejection to LessonsStore
   - Similar suggestions will be less frequent in the future

## WSL2 Support

Shadow Agent works in WSL2, but with limitations:
- ✅ **Clipboard**: Works via pyperclip (native Windows API)
- ⚠️ **Window tracking**: Requires satellite on Windows
- ⚠️ **Notifications**: Requires bridge via powershell.exe

### Optional Satellite for WSL2
For full functionality in WSL2, run `venom_satellite.py` on Windows:
```python
# venom_satellite.py (run on Windows)
# Monitors windows and sends data to Venom in WSL via HTTP

import requests
import win32gui

while True:
    window_title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
    requests.post("http://localhost:8000/api/v1/shadow/window",
                  json={"title": window_title})
    time.sleep(1)
```

## Demo

Run the demo to see Shadow Agent in action:
```bash
cd /home/runner/work/Venom/Venom
PYTHONPATH=/home/runner/work/Venom/Venom python examples/shadow_demo.py
```

Demo shows:
- Privacy Filter in action
- Code error detection
- Suggestion generation with different types
- Status of all components

## Tests

Run tests:
```bash
pytest tests/test_desktop_sensor.py tests/test_shadow_agent.py tests/test_notifier.py -v
```

**Test Coverage:**
- 16 Desktop Sensor tests
- 16 Shadow Agent tests
- 10 Notifier tests
- **42 tests total - all ✅**

## Roadmap

### Planned Features
- [ ] Integration with Eyes for OCR from screenshots
- [ ] Deeper integration with GoalStore (auto task updates)
- [ ] More suggestion types (DocumentationNeeded, TestCoverage)
- [ ] Dashboard UI for Ghost Mode
- [ ] WSL2 satellite (Python service on Windows)
- [ ] Machine Learning for better confidence scoring
- [ ] Context window with activity history

### Known Limitations
- Shadow Agent uses simple heuristics + LLM (may have false positives)
- Windows Toast requires win10toast or PowerShell
- WSL2 requires bridge/satellite for full functionality
- Credit card detection may have false positives (no Luhn validation)

## Contributing

Report issues and PRs on GitHub:
- Bug reports: Issues with `shadow-agent` tag
- Feature requests: Issues with `enhancement` tag
- Security issues: Private security advisories

## License

Part of Venom project - see main README.md

---

**Status:** ✅ Production Ready
**Last Updated:** 2025-12-08
**Version:** 1.0.0
