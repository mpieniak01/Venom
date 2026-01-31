# The Apprentice - Visual Imitation Learning Guide

## Overview

**The Apprentice** is a revolutionary Venom feature enabling learning of new skills through observation of user actions. Instead of manually programming automation scripts, the operator performs the task and Venom "watches and learns".

## Architecture

The system consists of four main components:

### 1. Demonstration Recorder (`venom_core/perception/recorder.py`)

The recorder captures user demonstrations:
- **Screenshots** - taken at action moments (mss library)
- **Mouse events** - clicks, positions (pynput)
- **Keyboard events** - typed text, shortcuts (pynput)

Data is saved as a session (`session.json` + directory with screenshots).

```python
from venom_core.perception.recorder import DemonstrationRecorder

recorder = DemonstrationRecorder()

# Start recording
session_id = recorder.start_recording(session_name="my_workflow")

# [User performs actions]

# Stop recording
session_path = recorder.stop_recording()
```

### 2. Demonstration Analyzer (`venom_core/learning/demonstration_analyzer.py`)

The analyzer transforms raw data into semantic actions:
- Transforms pixel coordinates → UI element descriptions
- Recognizes key sequences (text vs shortcuts)
- Detects sensitive data (passwords)
- Generates `ActionIntent` (semantic steps)

```python
from venom_core.learning.demonstration_analyzer import DemonstrationAnalyzer

analyzer = DemonstrationAnalyzer()

# Analyze session
session = recorder.load_session(session_id)
actions = await analyzer.analyze_session(session)

# actions is a list of ActionIntent with semantic descriptions
```

### 3. Apprentice Agent (`venom_core/agents/apprentice.py`)

Agent manages the entire learning cycle:
- Controls recording (REC/STOP)
- Analyzes demonstrations
- Generates Python scripts
- Parameterizes workflows
- Saves to `custom_skills/`

```python
from venom_core.agents.apprentice import ApprenticeAgent

apprentice = ApprenticeAgent(kernel)

# Start recording
await apprentice.process("Start recording named login_workflow")

# [Demonstration]

# Stop and analyze
await apprentice.process("Stop recording")
await apprentice.process("Analyze session login_workflow")

# Generate skill
await apprentice.process("Generate skill login_to_app")
```

### 4. Workflow Store (`venom_core/memory/workflow_store.py`)

Storage manages workflows:
- Save/load workflows (JSON)
- CRUD operations on steps
- Export to Python
- Workflow search

```python
from venom_core.memory.workflow_store import WorkflowStore

store = WorkflowStore()

# List workflows
workflows = store.list_workflows()

# Load workflow
workflow = store.load_workflow("my_workflow")

# Edit step
store.update_step("my_workflow", step_id=1, updates={"enabled": False})

# Export to Python
python_file = store.export_to_python("my_workflow")
```

## User Workflow

### Step 1: Demonstration

```
User: "Venom, watch how I send a report to Slack"
Venom: "🔴 Started recording demonstration (session: send_report_slack)"

[User]:
1. Opens Slack
2. Clicks #general channel
3. Clicks paperclip icon (attach)
4. Selects file report.pdf
5. Clicks "Send"

User: "Done"
Venom: "⬛ Recording completed (5 actions, 32 seconds)"
```

### Step 2: Analysis

```
Venom: "Analyzing demonstration..."
Venom: "I understood workflow consisting of 5 steps:
  1. Click Slack icon on taskbar
  2. Click #general channel
  3. Click attachment button (paperclip icon)
  4. Select file: report.pdf
  5. Click Send button
"
```

### Step 3: Parameterization

```
Venom: "I noticed value 'report.pdf'. Should this be a parameter?"
User: "Yes, name it 'filename'"
Venom: "OK, I'll create parameter 'filename' with default value 'report.pdf'"
```

### Step 4: Skill Generation

```
Venom: "Generating skill 'send_report_slack'..."
Venom: "✅ Skill generated: workspace/custom_skills/send_report_slack.py"
```

### Step 5: Execution

```
User: "Venom, send report to Slack"
Venom: "Executing workflow send_report_slack..."
[GhostAgent executes generated code]
Venom: "✅ Report sent successfully"
```

## Usage Examples

### Example 1: Application Login

```python
# 1. Record demonstration
await apprentice.process("Start recording named bank_login")

# User:
# - Opens browser
# - Types URL
# - Clicks username field
# - Types username
# - Clicks password field
# - Types password
# - Clicks Login button

await apprentice.process("Stop recording")

# 2. Analyze and generate
await apprentice.process("Analyze session bank_login")
await apprentice.process("Generate skill bank_login_skill")

# 3. Generated code (workspace/custom_skills/bank_login_skill.py):
"""
async def bank_login_skill(ghost_agent: GhostAgent, **kwargs):
    username = kwargs.get("username", "user@example.com")
    password = kwargs.get("password", "")

    await ghost_agent.vision_click(description="browser icon")
    await ghost_agent.input_skill.keyboard_type(text="https://bank.example.com")
    await ghost_agent.input_skill.keyboard_hotkey(["enter"])

    await ghost_agent.vision_click(description="username field")
    await ghost_agent.input_skill.keyboard_type(text=username)

    await ghost_agent.vision_click(description="password field")
    await ghost_agent.input_skill.keyboard_type(text=password)

    await ghost_agent.vision_click(description="login button")
"""
```

### Example 2: Data Export

```python
# Demonstration:
# 1. Open Excel
# 2. File → Export → CSV
# 3. Choose location
# 4. Save

await apprentice.process("Start recording named excel_export")
# [Demonstration]
await apprentice.process("Stop recording")
await apprentice.process("Generate skill excel_to_csv")

# Usage:
await ghost.process("Execute skill excel_to_csv")
```

## Advanced Features

### Workflow Editing

After generation, workflows can be edited:

```python
from venom_core.memory.workflow_store import WorkflowStore, WorkflowStep

store = WorkflowStore()

# Add step (wait)
new_step = WorkflowStep(
    step_id=0,
    action_type="wait",
    description="Wait 2 seconds for page to load",
    params={"duration": 2.0},
)
store.add_step("my_workflow", new_step, position=3)

# Disable step
store.update_step("my_workflow", step_id=5, updates={"enabled": False})

# Change description
store.update_step("my_workflow", step_id=2, updates={
    "description": "Click UPDATED button"
})
```

### Workflow Search

```python
# Search by name/description
results = store.search_workflows("login")

# Result: list of workflows containing "login" in name or description
```

### Parameterization

The system automatically detects:
- **Constant values** (URL, paths) → hardcoded
- **Variable values** (user data) → parameters with default values
- **Sensitive data** (passwords) → required parameters (no default value)

```python
# Password detection heuristic:
# - No spaces
# - Contains digits
# - Contains special characters
# - Short text (< 20 characters)
```

## Security and Privacy

### Password Masking

System automatically detects probable passwords:

```python
# In demonstration:
# User types: "MyP@ssw0rd!"

# In analysis:
action = ActionIntent(
    action_type="type",
    description="Type text: ***",  # Masked
    params={
        "text": "MyP@ssw0rd!",
        "is_sensitive": True  # Marked as sensitive
    }
)

# In generated code:
# password = kwargs.get("password", "")  # No default value
```

### Screenshot Privacy

Screenshots stored locally in `workspace/demonstrations/`.
Can be manually deleted after skill generation.

## GhostAgent Integration

Generated scripts use GhostAgent API:

- `vision_click(description, fallback_coords)` - element click
- `input_skill.keyboard_type(text)` - text input
- `input_skill.keyboard_hotkey(keys)` - keyboard shortcut
- `_wait(duration)` - delay

### Position Resilience

Code uses element descriptions instead of fixed coordinates:

```python
# ❌ Not resilient (fixed coordinates)
await ghost.input_skill.mouse_click(x=500, y=300)

# ✅ Resilient (element description + fallback)
await ghost.vision_click(
    description="blue Submit button",
    fallback_coords=(500, 300)  # Fallback if not found
)
```

## Limitations and Roadmap

### Current Limitations

- UI element recognition requires further integration with Florence-2/LLaVA
- No OCR for automatic button text detection
- No automatic validation of generated workflows

### Planned Features

- **Dashboard UI**: Web interface with REC/STOP buttons, timeline, editor
- **Florence-2 Integration**: Better UI element recognition
- **OCR**: Automatic button text detection
- **Validation**: Automatic testing of generated workflows
- **Multi-monitor Support**: Multiple monitor support
- **Conditional Steps**: Conditional steps (if/else)

## API Reference

### DemonstrationRecorder

```python
recorder = DemonstrationRecorder(workspace_root="./workspace")

# Start recording
session_id = recorder.start_recording(
    session_name="my_session",
    metadata={"description": "Login workflow"}
)

# Stop recording
session_path = recorder.stop_recording()

# Load session
session = recorder.load_session(session_id)

# List sessions
sessions = recorder.list_sessions()
```

### DemonstrationAnalyzer

```python
analyzer = DemonstrationAnalyzer()

# Analyze session
actions = await analyzer.analyze_session(session)

# Generate description
summary = analyzer.generate_workflow_summary(actions)
```

### ApprenticeAgent

```python
apprentice = ApprenticeAgent(kernel, workspace_root="./workspace")

# Process commands
await apprentice.process("Start recording")
await apprentice.process("Stop recording")
await apprentice.process("Analyze session <session_id>")
await apprentice.process("Generate skill <skill_name>")
```

### WorkflowStore

```python
store = WorkflowStore(workspace_root="./workspace")

# CRUD
workflow = store.load_workflow(workflow_id)
store.save_workflow(workflow)
store.delete_workflow(workflow_id)

# Step operations
store.add_step(workflow_id, step, position=None)
store.update_step(workflow_id, step_id, updates)
store.remove_step(workflow_id, step_id)

# Export
python_path = store.export_to_python(workflow_id)

# Search
results = store.search_workflows(query)
```

## Troubleshooting

### Problem: Recording doesn't start

**Cause**: No permissions to capture events
**Solution**: Run with administrator privileges (Windows) or as sudo (Linux)

### Problem: Screenshots are empty

**Cause**: mss library issue in headless environment
**Solution**: Use GUI environment or change backend to PIL.ImageGrab

### Problem: Generated code doesn't work

**Cause**: Inappropriate element descriptions
**Solution**:
1. Check analysis logs
2. Manually edit workflow in WorkflowStore
3. Add more detailed element descriptions

## Examples

See complete examples in:
- `examples/apprentice_demo.py` - basic demo
- `examples/apprentice_integration_example.py` - GhostAgent integration

## Support

In case of issues:
1. Check logs: `data/logs/venom.log`
2. Run demo: `python examples/apprentice_demo.py`
3. Report issue on GitHub
