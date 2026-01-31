# THE EXECUTIVE - Management and Strategy Layer

## Overview

**The Executive** is the highest layer in Venom's hierarchy, transforming the system from a "task executor" into a "project manager". It introduces autonomous project management with hierarchical goal structure and automatic roadmap execution.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    THE EXECUTIVE LAYER                       │
│                                                              │
│  ┌────────────────┐    ┌────────────────┐   ┌────────────┐ │
│  │ ExecutiveAgent │───►│   GoalStore    │◄──│  War Room  │ │
│  │   (CEO/PM)     │    │  (Roadmap)     │   │ Dashboard  │ │
│  └────────────────┘    └────────────────┘   └────────────┘ │
│         │                      │                    │        │
│         └──────────────────────┼────────────────────┘        │
│                                │                              │
└────────────────────────────────┼──────────────────────────────┘
                                 │
                        ┌────────▼────────┐
                        │  Orchestrator   │
                        │  (Campaign Mode)│
                        └─────────────────┘
                                 │
                        ┌────────▼────────┐
                        │  The Council    │
                        │  Architect      │
                        │  Coder          │
                        │  Guardian       │
                        └─────────────────┘
```

## Components

### 1. GoalStore (`venom_core/core/goal_store.py`)

Storage for hierarchical project goal structure.

**Hierarchy:**
- **Vision** - Overarching long-term goal
- **Milestone** - Implementation stages
- **Task** - Specific tasks to complete

**KPI (Key Performance Indicators):**
- Success metrics for each goal
- Automatic progress calculation

**Persistence:**
- JSON storage in `data/memory/roadmap.json`
- Automatic change saving

**API:**
```python
goal_store = GoalStore()

# Add vision
vision = goal_store.add_goal(
    title="Create best AI framework",
    goal_type=GoalType.VISION,
    description="...",
    kpis=[KPI(name="Progress", target_value=100.0, unit="%")]
)

# Add milestone
milestone = goal_store.add_goal(
    title="Implement Executive Layer",
    goal_type=GoalType.MILESTONE,
    parent_id=vision.goal_id,
    priority=1
)

# Get next task
next_task = goal_store.get_next_task()

# Update progress
goal_store.update_progress(
    task.goal_id,
    status=GoalStatus.COMPLETED
)

# Generate report
report = goal_store.generate_roadmap_report()
```

### 2. ExecutiveAgent (`venom_core/agents/executive.py`)

Top-level agent - system's CEO/Product Manager.

**Role:**
- Transforming vision into roadmap
- Task prioritization
- Agent team management
- Project status reporting

**Key Methods:**
```python
executive = ExecutiveAgent(kernel, goal_store)

# Create roadmap from vision
roadmap = await executive.create_roadmap(
    "I want to create the best AI system"
)

# Generate status report
status = await executive.generate_status_report()

# Run Daily Standup
meeting = await executive.run_status_meeting()

# Prioritize tasks
priorities = await executive.prioritize_tasks(milestone_id)
```

### 3. Campaign Mode

Autonomous roadmap execution loop in `Orchestrator`.

**Algorithm:**
```
LOOP (max_iterations):
    1. Get next task from GoalStore
    2. Execute task (delegate to agents)
    3. Verify results (Guardian)
    4. Update progress in GoalStore
    5. If Milestone completed:
       - Pause for user acceptance
       - Move to next Milestone
    6. If all goals achieved:
       - SUCCESS - end campaign
```

**Usage:**
```python
# Run campaign
result = await orchestrator.execute_campaign_mode(
    goal_store=goal_store,
    max_iterations=10
)
```

### 4. War Room Dashboard (`web/templates/strategy.html`)

Visual strategic dashboard for project management.

**Sections:**
- **Vision Panel** - Displays main vision and progress
- **Milestones Panel** - Milestone list with status
- **Tasks List** - Tasks within milestone
- **KPI Dashboard** - Success indicators
- **Actions** - Management buttons

**Access:**
```
http://localhost:8000/strategy
```

## Workflow

### 1. Defining Vision

User defines project vision:

```
"I want to create the best AI framework for task automation"
```

ExecutiveAgent automatically generates:
- Vision (Main vision)
- 3-5 Milestones (Stages)
- 3-5 Tasks for first Milestone

### 2. Launching Campaign

System enters autonomous mode:

1. **Iteration 1:**
   - Gets Task 1 from Milestone 1
   - Delegates to Coder/Guardian
   - Tests and verifies
   - Marks as COMPLETED

2. **Iteration 2:**
   - Gets Task 2
   - ...

3. **Milestone completed:**
   - Pause for acceptance
   - Waits for user confirmation
   - Proceeds to Milestone 2

### 3. Daily Standup

Automatic status meeting (daily):

```python
scheduler.schedule_daily_standup(
    executive_agent=executive,
    goal_store=goal_store,
    hour=9,
    minute=0
)
```

Report contains:
- Current Milestone status
- Completed/Pending/Blocked tasks
- Blockers (if any)
- Next task to execute
- Executive decisions

### 4. Reporting

Generating management reports:

```python
report = await executive.generate_status_report()
```

Format:
```
=== PROJECT ROADMAP ===

🎯 VISION: Create best AI framework
   Status: IN_PROGRESS
   Progress: 45.0%

📋 MILESTONES (3):

  1. 🔄 [1] Implement Executive Layer
      Progress: 90.0% | IN_PROGRESS
      Tasks: 4/5 completed

  2. ⏸️ [2] Integrate with GitHub
      Progress: 0.0% | PENDING
      Tasks: 0/3 completed

📊 SUMMARY: 0/3 milestones completed (0.0%)
```

## API Endpoints

### GET /strategy
Serves War Room dashboard

### GET /api/roadmap
Gets complete roadmap
```json
{
  "vision": {...},
  "milestones": [...],
  "kpis": {...},
  "report": "..."
}
```

### POST /api/roadmap/create
Creates roadmap from vision
```json
{
  "vision": "Create best AI framework"
}
```

### GET /api/roadmap/status
Generates Executive status report

### POST /api/campaign/start
Starts Campaign Mode

## Intent Manager Integration

New intents:

**START_CAMPAIGN:**
```
"Start campaign"
"Launch autonomous mode"
"Continue project work"
```

**STATUS_REPORT:**
```
"What is project status?"
"Show progress"
"Where are we with execution?"
```

## Usage Examples

### Scenario 1: New Project

```python
# 1. User defines vision
vision = "Create server monitoring system"

# 2. Executive creates roadmap
roadmap = await executive.create_roadmap(vision)

# 3. System launches campaign
campaign = await orchestrator.execute_campaign_mode(goal_store)

# 4. Venom autonomously executes consecutive tasks
# - Milestone 1: Backend API
#   - Task 1: Setup FastAPI ✅
#   - Task 2: Database models ✅
#   - Task 3: Authentication ✅
# - Milestone 2: Frontend Dashboard
#   ...
```

### Scenario 2: Status Check

```
User: "What is project status?"

Executive: "We're at 60% completion of Milestone 1 (Backend API).
Completed 3/5 tasks. Currently working on database integration.
No blockers. Expected completion: ~2 days."
```

### Scenario 3: Human-in-the-loop

```
[Milestone 1 completed]

System: "Milestone 1 'Backend API' ready. Can I start Milestone 2 'Frontend'?"

User: "Yes, continue"

System: [Starts Milestone 2]
```

## Configuration

In `venom_core/config.py`:
```python
# Executive Layer settings
GOAL_STORE_PATH = "data/memory/roadmap.json"
CAMPAIGN_MAX_ITERATIONS = 10
DAILY_STANDUP_HOUR = 9
DAILY_STANDUP_MINUTE = 0
```

## Security

- **Human-in-the-loop:** System pauses after each Milestone
- **Max iterations:** Iteration limit prevents infinite loops
- **Budget control:** User controls token budget
- **Validation:** Guardian verifies each task

## Future Extensions

- **GitHub Issues sync:** Automatic synchronization with GitHub Issues
- **Slack notifications:** Progress notifications
- **Multi-project support:** Managing multiple projects
- **Team collaboration:** Sharing roadmaps between team members
- **Advanced KPIs:** Code quality metrics, performance, coverage
- **AI-powered estimation:** Automatic execution time estimation

## See Also

- [THE_COUNCIL.md](THE_COUNCIL.md) - Agent collaboration
- [THE_OVERMIND.md](THE_OVERMIND.md) - Scheduling system
- [CORE_NERVOUS_SYSTEM_V1.md](CORE_NERVOUS_SYSTEM_V1.md) - System architecture
