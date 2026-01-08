# AutonomyGate - Permission Control System

## 📋 Introduction

AutonomyGate is a 5-level agent permission control system that replaces the binary "Cost Mode". The system manages network access, budget, and file/operating system modification rights.

## 🚦 Autonomy Levels

The system defines 5 trust levels, where each higher level inherits permissions from lower ones:

### Level 0: ISOLATED (🟢 Green)
- **Scope**: Local Read
- **Permissions**:
  - ✅ Local file access (read-only)
  - ✅ Local models (Ollama, vLLM)
  - ✅ RAG memory (local)
  - ❌ No network access
  - ❌ No file writing
- **Risk**: Zero
- **Example Skills**: `FileRead`, `MemoryRecall`, `LocalLlm`

### Level 10: CONNECTED (🔵 Blue)
- **Scope**: Internet (Free)
- **Permissions**:
  - ✅ Everything from ISOLATED level
  - ✅ Public network access
  - ✅ Free APIs (DuckDuckGo, Wikipedia)
  - ✅ Web browser
  - ❌ Still no file writing
- **Risk**: Low (data leak)
- **Example Skills**: `DuckDuckGo`, `BrowserVisit`, `WeatherApi`

### Level 20: FUNDED (🟡 Yellow)
- **Scope**: Paid APIs (Cloud)
- **Permissions**:
  - ✅ Everything from CONNECTED level
  - ✅ Paid cloud APIs (GPT-4, Gemini)
  - ✅ Expense authorization (Token Economist)
  - ✅ SOTA AI models
  - ❌ Still no file writing
- **Risk**: Medium (financial costs)
- **Example Skills**: `GPT-4o`, `Gemini Pro`, `DeepL`, `DALL-E`

### Level 30: BUILDER (🟠 Orange)
- **Scope**: File Editing
- **Permissions**:
  - ✅ Everything from FUNDED level
  - ✅ File creation and modification
  - ✅ Project code editing
  - ✅ Git commit/push
  - ❌ No system terminal access
- **Risk**: High (code errors)
- **Example Skills**: `FileWrite`, `FileEdit`, `GitCommit`

### Level 40: ROOT (🔴 Red)
- **Scope**: Full Power
- **Permissions**:
  - ✅ Everything from BUILDER level
  - ✅ System shell access
  - ✅ Docker, package installation
  - ✅ Full system control
- **Risk**: Critical (system destruction)
- **Example Skills**: `ShellExecute`, `DockerRun`, `PipInstall`

## 🛠️ Implementation

### Backend

#### 1. PermissionGuard

Singleton managing permission system:

```python
from venom_core.core.permission_guard import permission_guard, AutonomyViolation

# Check permissions
try:
    permission_guard.check_permission("ShellSkill")
    # If permissions sufficient, execute action
except AutonomyViolation as e:
    # No permissions - return 403 error to frontend
    print(f"Required level: {e.required_level_name}")
```

#### 2. StateManager

Autonomy level persistence:

```python
from venom_core.core.state_manager import StateManager

state_manager = StateManager()
print(f"Current level: {state_manager.autonomy_level}")
```

#### 3. API Endpoints

```bash
# Get current level
GET /api/v1/system/autonomy

# Set new level
POST /api/v1/system/autonomy
{
  "level": 20
}

# List all levels
GET /api/v1/system/autonomy/levels
```

### Frontend

#### 1. Autonomy Selector

In `index.html`:

```html
<select id="autonomyLevel" class="autonomy-select">
    <option value="0" data-color="green">🟢 ISOLATED</option>
    <option value="10" data-color="blue">🔵 CONNECTED</option>
    <option value="20" data-color="yellow">🟡 FUNDED</option>
    <option value="30" data-color="orange">🟠 BUILDER</option>
    <option value="40" data-color="red">🔴 ROOT</option>
</select>
```

#### 2. Dynamic Theming

Body element has theme class:

```html
<body class="theme-isolated" id="venomBody">
```

Theme classes define colors:
- `.theme-isolated` - green
- `.theme-connected` - blue
- `.theme-funded` - yellow
- `.theme-builder` - orange
- `.theme-root` - red

#### 3. Error Handling

When backend returns `403 Autonomy Violation`:

1. Frontend displays modal with required level information
2. Autonomy selector pulses with appropriate color
3. User can increase level or cancel

## 📊 Usage Scenario

### Example: Check Weather and Save to File

```
1. START: System at ISOLATED level (0)

2. User: "Check weather in Warsaw"
   - Backend: PermissionGuard.check_permission("WebSkill")
   - Result: AutonomyViolation (required level 10)
   - Frontend: Modal + blue pulsation

3. User increases level to CONNECTED (10)
   - Backend: permission_guard.set_level(10)
   - Frontend: Theme changes to blue

4. User again: "Check weather in Warsaw"
   - Backend: Permissions OK, executes WebSkill
   - Result: Weather data retrieved

5. User: "Save this to file weather.txt"
   - Backend: PermissionGuard.check_permission("FileWriteSkill")
   - Result: AutonomyViolation (required level 30)
   - Frontend: Modal + orange pulsation

6. User increases level to BUILDER (30)
   - Backend: permission_guard.set_level(30)
   - Frontend: Theme changes to orange

7. User again: "Save this to file weather.txt"
   - Backend: Permissions OK, executes FileWriteSkill
   - Result: File saved
```

## 🔒 Security Rules

### 1. Default Level: ISOLATED

System always starts at ISOLATED level (0) for maximum security.

### 2. New Tools = ROOT

New, uncategorized skills default to requiring ROOT level (40):

```python
# UnknownSkill not in skill_permissions.yaml
# PermissionGuard defaults to requiring level 40
permission_guard.check_permission("UnknownSkill")  # Requires ROOT
```

### 3. Explicit > Implicit

Better to explicitly set lower level for safe skill than rely on default ROOT:

```yaml
# skill_permissions.yaml
SafeReadOnlySkill: 0  # Explicit - safe
```

### 4. Audit and Monitoring

- Each level change is logged
- StateManager persists level between sessions
- TokenEconomist automatically enables/disables paid mode at level 20+

## 📁 Configuration Files

### autonomy_matrix.yaml

Autonomy level definitions:

```yaml
levels:
  - id: 0
    name: "ISOLATED"
    description: "Local Read"
    color: "#22c55e"
    permissions:
      network_enabled: false
      paid_api_enabled: false
      filesystem_mode: "read_only"
      shell_enabled: false
```

### skill_permissions.yaml

Skill to level mapping:

```yaml
FileReadSkill: 0
WebSearchSkill: 10
GeminiSkill: 20
FileWriteSkill: 30
ShellSkill: 40
```

## 🧪 Testing

Run tests:

```bash
pytest tests/test_permission_guard.py -v
```

Key tests:
- ✅ Singleton pattern
- ✅ Level setting
- ✅ Permission checking
- ✅ Permission inheritance
- ✅ Blocking unauthorized actions
- ✅ Default ROOT requirement for unknown skills

## 🎯 Best Practices

1. **Start Safe**: Always begin session at ISOLATED level
2. **Incremental Elevation**: Increase level only when needed
3. **Explicit Permissions**: Define permissions for new skills in `skill_permissions.yaml`
4. **User Confirmation**: Frontend requires conscious user consent for level change
5. **Audit Trail**: Monitor level changes in logs

## 📚 References

- **Backend Code**: `venom_core/core/permission_guard.py`
- **Frontend Code**: `web/static/js/app.js` (AutonomyGate section)
- **Configuration**: `data/config/autonomy_matrix.yaml`, `data/config/skill_permissions.yaml`
- **Tests**: `tests/test_permission_guard.py`
- **API**: `venom_core/api/routes/system.py` (`/api/v1/system/autonomy` endpoints)
