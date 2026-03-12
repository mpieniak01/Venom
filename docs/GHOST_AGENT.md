# Ghost Agent - Visual GUI Automation (Task 032)

## 🎯 Overview

Ghost Agent (The Ghost) is a revolutionary Venom feature enabling **physical interaction with the operating system interface**. The agent "possesses" the mouse cursor and keyboard to perform tasks in applications without APIs (e.g., Spotify, Excel, Photoshop, legacy software).

## 🏗️ Architecture

### Components

1. **VisionGrounding** (`venom_core/perception/vision_grounding.py`)
   - UI element localization based on visual descriptions
   - GPT-4o Vision (OpenAI) support or OCR fallback
   - Returns coordinates (x, y) of found element

2. **InputSkill** (`venom_core/execution/skills/input_skill.py`)
   - Mouse control (clicking, double-clicking, movement)
   - Keyboard control (typing, hotkeys)
   - **Fail-Safe Protection** (PyAutoGUI)

3. **GhostAgent** (`venom_core/agents/ghost_agent.py`)
   - RPA agent with OODA loop (Observe-Orient-Decide-Act)
   - Planning and executing action sequences
   - Generating task execution reports

4. **DesktopSensor** (extended)
   - User action recording mode
   - Replay/macros for GhostAgent

## 🔐 Security

### PyAutoGUI Fail-Safe
**CRITICAL:** Ghost Agent has built-in protection:
- Moving mouse to screen corner **(0, 0)** IMMEDIATELY interrupts all operations
- Fail-Safe is **ALWAYS ACTIVE** and cannot be disabled
- This is a protective mechanism against uncontrolled agent behavior

### Other protections
- Coordinate validation (checking if within screen bounds)
- Delays between actions (default 0.5s)
- Logging all operations
- Maximum step limit (default 20)
- Emergency Stop API

## 📝 Configuration

In `.env` or `config.py` file:

```python
# Ghost Agent (Visual GUI Automation)
ENABLE_GHOST_AGENT = False  # Enable Ghost Agent
ENABLE_GHOST_API = False  # Enable public API endpoints /api/v1/ghost/*
GHOST_MAX_STEPS = 20  # Maximum number of steps
GHOST_STEP_DELAY = 1.0  # Delay between steps (seconds)
GHOST_VERIFICATION_ENABLED = True  # Verification after each step
GHOST_SAFETY_DELAY = 0.5  # Safety delay
GHOST_VISION_CONFIDENCE = 0.7  # Confidence threshold for vision grounding
GHOST_RUNTIME_PROFILE = "desktop_safe"  # desktop_safe|desktop_power
GHOST_CRITICAL_FAIL_CLOSED = True  # Block fallback clicks in critical paths

# OpenAI API (optional, for vision grounding)
OPENAI_API_KEY = "sk-..."  # If you want to use GPT-4o Vision
```

### Runtime profiles

- `desktop_safe`:
  - conservative limits,
  - verification enabled,
  - fail-closed behavior for critical actions.
- `desktop_power`:
  - higher throughput defaults,
  - faster step pacing,
  - fallback allowed when visual match is missing.

### Governance and audit

- `InputSkill` desktop mutations (`mouse_click`, `keyboard_type`, `keyboard_hotkey`) are protected by autonomy policy checks.
- Ghost runtime and API publish canonical audit entries:
  - desktop actions: `source=core.ghost`,
  - API control plane: `source=api.ghost`.

## 🚀 Usage Examples

### Example 1: Open Notepad and write text

```python
from venom_core.agents.ghost_agent import GhostAgent
from venom_core.execution.kernel_builder import KernelBuilder

# Build kernel
kernel = KernelBuilder().build()

# Create Ghost Agent
ghost = GhostAgent(
    kernel=kernel,
    max_steps=20,
    step_delay=1.0,
)

# Execute task
result = await ghost.process("Open notepad and write 'Hello Venom'")
print(result)
```

**Output:**
```
📊 GHOST AGENT REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Steps executed: 7
Successful: 7 ✅
Failed: 0 ❌

DETAILS:
1. ✅ Open Run dialog
   → ✅ Executed hotkey: win+r
2. ✅ Wait for opening
   → Waited 1.0s
3. ✅ Type 'notepad'
   → ✅ Typed text (7 characters)
4. ✅ Press Enter
   → ✅ Executed hotkey: enter
5. ✅ Wait for notepad
   → Waited 2.0s
6. ✅ Type text: Hello Venom
   → ✅ Typed text (12 characters)
```

### Example 2: Play next song in Spotify

```python
result = await ghost.process("Play next song in Spotify")
```

**How it works:**
1. Ghost takes screenshot of screen
2. VisionGrounding locates "Next" button in Spotify
3. InputSkill clicks found button
4. Music changes ✅

### Example 3: Using InputSkill directly

```python
from venom_core.execution.skills.input_skill import InputSkill

input_skill = InputSkill(safety_delay=0.5)

# Click at point (500, 300)
await input_skill.mouse_click(x=500, y=300)

# Type text
await input_skill.keyboard_type("Hello World", interval=0.1)

# Execute Ctrl+S shortcut
await input_skill.keyboard_hotkey("ctrl+s")

# Get mouse position
position = await input_skill.get_mouse_position()
print(position)  # "Mouse position: (500, 300)"
```

### Example 4: Vision Grounding

```python
from venom_core.perception.vision_grounding import VisionGrounding
from PIL import ImageGrab

vision = VisionGrounding()

# Take screenshot
screenshot = ImageGrab.grab()

# Find element
coords = await vision.locate_element(
    screenshot,
    description="green Save button"
)

if coords:
    x, y = coords
    print(f"Element found: ({x}, {y})")
else:
    print("Element not found")
```

### Example 5: `vision_click` with fallback policy

```python
# Safe mode: fail-closed if description is not found
ghost.apply_runtime_profile("desktop_safe")
await ghost.vision_click(
    description="blue Submit button",
    fallback_coords=(500, 300),
)

# Power mode: fallback may be used when locate fails
ghost.apply_runtime_profile("desktop_power")
await ghost.vision_click(
    description="blue Submit button",
    fallback_coords=(500, 300),
    require_visual_confirmation=False,
)
```

### Ghost API contract (feature-flagged)

When `ENABLE_GHOST_API=True` and `ENABLE_GHOST_AGENT=True`:

- `GET /api/v1/ghost/status` - runtime + execution status
- `POST /api/v1/ghost/start` - start background Ghost task
- `POST /api/v1/ghost/cancel` - cancel active task (emergency stop)

## 🧪 Testing

Run tests:

```bash
# All Ghost Agent tests
pytest tests/test_ghost_agent.py -v

# InputSkill tests
pytest tests/test_input_skill.py -v

# VisionGrounding tests
pytest tests/test_vision_grounding.py -v

# All tests together
pytest tests/test_ghost_agent.py tests/test_input_skill.py tests/test_vision_grounding.py -v
```

**Results:**
- 42 unit and integration tests
- 100% passing rate ✅

## ⚠️ Limitations and Known Issues

1. **Requires GUI Environment:**
   - Ghost Agent doesn't work in headless environments (without X11/Wayland)
   - Tests use mocks to work in CI/CD

2. **Vision Grounding:**
   - Requires OpenAI API key for best results
   - OCR fallback (pytesseract) has limited accuracy
   - Florence-2 not yet implemented (TODO)

3. **DPI Scaling:**
   - On systems with DPI scaling coordinate shifts may occur
   - TODO: Automatic DPI detection and compensation

4. **Performance:**
   - Image analysis through GPT-4o Vision takes 2-5 seconds
   - Ghost Agent is slower than human (intentionally, for safety)

## 🔮 Future Improvements

### Planned for future iterations:

1. **Florence-2 Integration**
   - Local vision model for offline action
   - Faster element localization (< 1s)

2. **DPI Auto-Compensation**
   - Automatic scaling detection and compensation

3. **Recording & Replay**
   - Recording user action sequences
   - Generalization to procedures/macros

4. **Dashboard Update**
   - Remote Control UI in browser
   - Live desktop streaming (MJPEG)
   - Emergency Stop button

5. **Advanced Planning**
   - LLM-based action planning
   - Multi-step reasoning for complex tasks

## 📚 API Reference

### GhostAgent

```python
class GhostAgent(BaseAgent):
    def __init__(
        kernel: Kernel,
        max_steps: int = 20,
        step_delay: float = 1.0,
        verification_enabled: bool = True
    )

    async def process(input_text: str) -> str
    async def vision_click(
        description: str,
        fallback_coords: tuple[int, int] | None = None
    ) -> Dict[str, Any]
    def apply_runtime_profile(profile: str) -> Dict[str, Any]
    def emergency_stop_trigger() -> None
    def get_status() -> Dict[str, Any]
```

### InputSkill

```python
class InputSkill:
    @kernel_function
    async def mouse_click(x: int, y: int, button: str = "left", double: bool = False) -> str

    @kernel_function
    async def keyboard_type(text: str, interval: float = 0.05) -> str

    @kernel_function
    async def keyboard_hotkey(keys: str) -> str

    @kernel_function
    async def get_mouse_position() -> str

    @kernel_function
    async def take_screenshot(region: Optional[str] = None) -> str
```

### VisionGrounding

```python
class VisionGrounding:
    async def locate_element(
        screenshot: Image.Image,
        description: str,
        confidence_threshold: float = 0.7
    ) -> Optional[Tuple[int, int]]

    def load_screenshot(path_or_bytes) -> Image.Image
```

## 🤝 Contributing

Ghost Agent is part of the Venom project. We encourage:
- Reporting Issues with problems/suggestions
- Pull Requests with improvements
- Testing and bug reporting

## 📄 License

See main Venom project LICENSE file.

---

**Note:** Ghost Agent is a powerful tool. Use responsibly and always test in a safe environment before running in production.
