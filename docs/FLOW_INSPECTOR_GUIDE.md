# Flow Inspector - User Guide

## 🔀 What is Flow Inspector?

Flow Inspector is a real-time visualization tool for Venom system's decision-making processes. It helps understand why the system made a specific decision (e.g., selected a particular agent, entered Council mode).

### Available version:

**Inspector (web-next)** (`/inspector`) - version in Next.js:
- React + Mermaid
- diagram zoom/pan (`react-zoom-pan-pinch`)
- telemetry panel and step filter
- full error data (`error_code`, `error_details`)

## ✨ Main Features

- **Dynamic visualization** - Mermaid.js Sequence Diagrams showing task flow
- **Decision Gates** - highlighted decision gates showing key points in flow
- **Real-time updates** - automatic refresh for tasks in progress
- **Task history** - browse all executed tasks with filters

## 🚀 How to use?

### 1. Accessing Flow Inspector

Navigate to Flow Inspector by clicking the link in navigation:

- **🔍 Inspector (web-next)**: `http://localhost:3000/inspector`

### 2. Interactive Inspector - Advanced features

#### Interface layout:

1. **Sidebar (left panel)** - Trace list (last 50 requests)
   - Status filters via badge and history list
   - Refresh buttons

2. **Diagram Panel (top main panel)** - Mermaid + zoom/pan
   - Controls: zoom in/out, reset
   - Content sanitization before render

3. **Telemetry Panel (bottom main panel)** - Context and errors
   - `error_code`, `error_details`, stage and retryable
   - Step list with text filter
   - "Contracts only" checkbox (execution_contract_violation)

#### Interactivity:

✅ **Zoom & Pan:**
- Mouse wheel - zoom in/out
- Mouse drag - move diagram
- Buttons 🔍+/🔍-/↺ - zoom controls

✅ **Step list + telemetry panel:**
- Click step in list to see details and JSON
- Filter steps by content or contracts only

✅ **Decision Gates:**
- Highlighted with yellow background on diagram
- Emoji 🔀 in description
- Additional information in details panel

### 3. Selecting task for analysis

In "📋 Select task for analysis" section you'll see list of recent tasks:

- **Green border** - completed task (COMPLETED)
- **Red border** - failed task (FAILED)
- **Orange border** - task in progress (PROCESSING)
- **Blue border** - pending task (PENDING)

Click on the task you want to analyze.

### 3. Flow diagram analysis

After selecting a task you'll see:

#### 📊 Mermaid Diagram

Interactive sequence diagram showing:
- **Participants** - system components (User, Orchestrator, Agents)
- **Arrows** - communication flow between components
- **Yellow notes (Decision Gates)** - key decision points marked with emoji:
  - 🔀 Routing decision
  - 🏛️ Council Mode
  - 💻 Code Review Loop
  - 🚀 Campaign Mode
  - etc.

#### 🔍 Step Details

List of all steps with:
- **Component** - component name
- **Action** - performed action
- **Timestamp** - execution time
- **Details** - additional details

Decision Gates are highlighted with **orange background** and have **🔀 Decision Gate** badge.

### 4. Auto-refresh

Requires manual refresh with button.

## 🔒 Security

Inspector in web-next:
- Sanitizes content (components, actions, details) before Mermaid render.
- Renders diagrams in controlled component (no external CDN).
- Handles diagram fallback on render errors.

## 🎯 Usage Examples

### Agent selection analysis

```
User -> Orchestrator: "Write a sorting function"
Orchestrator -> IntentManager: classify_intent
Note over DecisionGate: 🔀 Route to Code Generation
Orchestrator -> CoderAgent: process_task
CoderAgent -> User: ✅ Task completed
```

**Decision Gate** shows that system recognized CODE_GENERATION intent and decided to use CoderAgent.

### Council mode analysis

```
User -> Orchestrator: "Create a complex web application"
Orchestrator -> IntentManager: classify_intent
Note over DecisionGate: 🏛️ Complex task -> Council Mode
Orchestrator -> CouncilFlow: run_discussion
CouncilFlow -> User: ✅ Task completed
```

**Decision Gate** shows that task was complex enough for system to activate Council mode.

### Error analysis

```
User -> Orchestrator: "Task with error"
Orchestrator -> Agent: process_task
Agent --x User: ❌ Task failed (Connection timeout)
```

Dashed line `--x` indicates error in flow.

## 🔧 API Endpoint

Flow Inspector uses REST API endpoint:

```
GET /api/v1/flow/{task_id}
```

**Response:**
```json
{
  "request_id": "uuid",
  "prompt": "Task content",
  "status": "COMPLETED",
  "created_at": "2024-12-10T13:00:00",
  "finished_at": "2024-12-10T13:00:05",
  "duration_seconds": 5.0,
  "steps": [
    {
      "component": "Orchestrator",
      "action": "classify_intent",
      "timestamp": "2024-12-10T13:00:01",
      "status": "ok",
      "details": "Intent: CODE_GENERATION",
      "is_decision_gate": false
    },
    {
      "component": "DecisionGate",
      "action": "select_code_review_loop",
      "timestamp": "2024-12-10T13:00:02",
      "status": "ok",
      "details": "💻 Routing to Coder-Critic Review Loop",
      "is_decision_gate": true
    }
  ],
  "mermaid_diagram": "sequenceDiagram\n..."
}
```

## 📝 Decision Gates - Types

System recognizes following Decision Gate types:

1. **route_help** - routing to help system (HELP_REQUEST)
2. **route_campaign** - routing to campaign mode (START_CAMPAIGN)
3. **select_council_mode** - Council mode selection for complex tasks
4. **select_code_review_loop** - Coder-Critic loop selection for code generation
5. **route_to_architect** - routing to Architect for complex planning
6. **route_to_agent** - standard routing to specific agent

## 💡 Tips & Tricks

### Flow Inspector (basic):
1. **Filtering** - use "🔄 Refresh" button to load latest tasks
2. **Live monitoring** - keep page open while executing task

### Interactive Inspector:
1. **Navigation** - use mouse wheel and dragging for large diagrams
2. **Exploration** - click elements to see JSON details
3. **Reset view** - ↺ button restores initial zoom settings
4. **Debugging** - details panel shows complete data for each step

### Both versions:
1. **Debugging** - Decision Gates help understand why system chose specific execution path
2. **History** - all tasks are saved, you can return to analyze older tasks

## 🐛 Troubleshooting

### No tasks in list
- Ensure RequestTracer is enabled in configuration
- Execute at least one task through system

### Diagram doesn't render
- Check JavaScript console in browser (F12)
- Ensure Mermaid.js is loaded (should be in base.html)
- **Interactive Inspector:** Check if CDN libraries are accessible (Alpine.js, svg-pan-zoom)

### No Decision Gates in diagram
- Ensure you're using latest Orchestrator version with enhanced logging
- Decision Gates are only added for tasks executed after this feature deployment

### Interactive Inspector - no interactivity
- Check JavaScript console - should see initialization messages
- Check internet connection (CDN libraries)
- Refresh page (Ctrl+F5)

### CSP (Content Security Policy) errors
- Interactive Inspector uses CDN - ensure CSP allows `cdn.jsdelivr.net`

## 🔗 Related Documents

- [REQUEST_TRACING_GUIDE.md](../REQUEST_TRACING_GUIDE.md) - request tracing system details
- [THE_COUNCIL.md](THE_COUNCIL.md) - Council mode documentation
- [INTENT_RECOGNITION.md](INTENT_RECOGNITION.md) - intent classification

## 📊 Example Scenarios

### Scenario 1: Simple request

```
User: "Hello!"
Intent: GENERAL_CHAT
Decision: Route to AssistantAgent
Result: Response from AssistantAgent
```

### Scenario 2: Complex project

```
User: "Create TODO app with React and FastAPI"
Intent: COMPLEX_PLANNING
Decision: Check complexity -> Council Mode activated
Result: Council discussion -> Architect plans -> Coder implements
```

### Scenario 3: Code generation with review

```
User: "Write fibonacci function"
Intent: CODE_GENERATION
Decision: Code Review Loop
Result: Coder generates -> Critic checks -> iterations -> acceptance
```

---

## 📚 Technologies

### Flow Inspector (basic):
- Vanilla JavaScript
- Mermaid.js (sequence diagrams)
- Fetch API

### Interactive Inspector:
- **Alpine.js 3.13.3** - reactive state management
- **svg-pan-zoom 3.6.1** - interactive diagram navigation
- **Mermaid.js 10.6.1** - sequence diagram rendering
- **Pure CSS3** - flexbox layout, no build tools required

---

**Version:** 2.0
**Date:** 2024-12-10
**Author:** Venom Team
