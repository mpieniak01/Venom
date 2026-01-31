# Dashboard v1.2 - Request Tracing Guide

## Overview

Request Tracing allows you to track the lifecycle of every task in Venom - from user submission, through each processing stage, to the final response.

## Architecture

### RequestTracer (`venom_core/core/tracer.py`)

Central module responsible for recording and storing execution traces.

**Key components:**
- `RequestTrace` - Single trace model (request_id, status, prompt, timestamps, steps)
- `TraceStep` - Single step model (component, action, timestamp, status, details)
- `TraceStatus` - Status enum: PENDING, PROCESSING, COMPLETED, FAILED, LOST
- `RequestTracer` - Main trace manager

**Watchdog mechanism:**
- Checks once per minute for inactive tasks
- If a PROCESSING task has no activity for 5 minutes → status becomes LOST
- Useful for detecting “lost” requests (e.g., after server restart)

**Thread safety:**
- All `_traces` operations are protected by a Lock
- Safe for async usage

### Orchestrator Integration

Orchestrator logs key execution steps automatically:

```python
# On submit_task
tracer.create_trace(task_id, prompt)
tracer.add_step(task_id, "User", "submit_request")

# When processing starts
tracer.update_status(task_id, TraceStatus.PROCESSING)
tracer.add_step(task_id, "Orchestrator", "start_processing")

# After intent classification
tracer.add_step(task_id, "Orchestrator", "classify_intent", details=f"Intent: {intent}")

# After agent processing
tracer.add_step(task_id, agent_name, "process_task")

# On completion
tracer.update_status(task_id, TraceStatus.COMPLETED)
tracer.add_step(task_id, "System", "complete", details="Response sent")

# On error
tracer.update_status(task_id, TraceStatus.FAILED)
tracer.add_step(task_id, "System", "error", status="error", details=str(e))
```

## API Endpoints

### GET `/api/v1/history/requests`

Returns a paginated list of requests.

**Parameters:**
- `limit` (int, optional): Max results (default 50)
- `offset` (int, optional): Pagination offset (default 0)
- `status` (str, optional): Filter by status (PENDING/PROCESSING/COMPLETED/FAILED/LOST)

**Response:**
```json
[
  {
    "request_id": "uuid",
    "prompt": "Task content...",
    "status": "COMPLETED",
    "created_at": "2024-12-09T08:00:00",
    "finished_at": "2024-12-09T08:00:15",
    "duration_seconds": 15.5
  }
]
```

### GET `/api/v1/history/requests/{request_id}`

Returns a detailed execution trace with all steps.

**Response:**
```json
{
  "request_id": "uuid",
  "prompt": "Task content...",
  "status": "COMPLETED",
  "created_at": "2024-12-09T08:00:00",
  "finished_at": "2024-12-09T08:00:15",
  "duration_seconds": 15.5,
  "llm_provider": "ollama",
  "llm_model": "gemma3:latest",
  "llm_endpoint": "http://localhost:11434/v1",
  "first_token": { "elapsed_ms": 740, "preview": "O" },
  "streaming": { "chunk_count": 120, "first_chunk_ms": 740, "last_emit_ms": 5200 },
  "steps": [
    {
      "component": "User",
      "action": "submit_request",
      "timestamp": "2024-12-09T08:00:00",
      "status": "ok",
      "details": "Request received"
    },
    {
      "component": "Orchestrator",
      "action": "classify_intent",
      "timestamp": "2024-12-09T08:00:01",
      "status": "ok",
      "details": "Intent: RESEARCH"
    },
    {
      "component": "LLM",
      "action": "start",
      "timestamp": "2024-12-09T08:00:02",
      "status": "ok",
      "details": "intent=GENERAL_CHAT"
    },
    {
      "component": "ResearcherAgent",
      "action": "process_task",
      "timestamp": "2024-12-09T08:00:10",
      "status": "ok",
      "details": "Task processed successfully"
    },
    {
      "component": "System",
      "action": "complete",
      "timestamp": "2024-12-09T08:00:15",
      "status": "ok",
      "details": "Response sent"
    }
  ]
}
```

## UI - History Tab

### Features

1. **Requests table**
   - Columns: Status (badge), Prompt (short), Created time + duration
   - Row coloring by status:
     - ⚪ White (PENDING) - new, not started
     - 🟡 Yellow (PROCESSING) - in progress
     - 🟢 Green (COMPLETED) - success
     - 🔴 Red (FAILED/LOST) - error or lost
   - Sort by newest
   - Click row to open details

2. **Details modal**
   - Basic info: ID, Status, Full prompt, timestamps, duration
   - Execution timeline:
     - Steps in chronological order
     - For each step: component, action, timestamp, details
     - Error visualization (red dot, red border)
     - Error details shown in a separate block

3. **Auto-refresh**
   - History loads automatically on tab open
   - “🔄” button for manual refresh

## Extending the system

### Add steps in your code

```python
# In an agent or skill
if self.tracer:
    self.tracer.add_step(
        request_id=task_id,
        component="MyAgent",
        action="custom_action",
        status="ok",  # or "error"
        details="Additional info"
    )
```

### Adding custom statuses

To add a new status, extend the `TraceStatus` enum in `tracer.py` and update the UI logic in:
- `app.js` - `getStatusIcon()`
- `app.css` - `.status-{name}` classes

## Best Practices

1. **Step logging:**
   - Log key moments (start, end, decisions)
   - Avoid too much granularity (not every line)
   - Add `details` for errors and important decisions

2. **Runtime consistency:**
   - Trace includes `Orchestrator.routing_resolved` with `provider/model/endpoint/hash`.
   - When config drift is detected, `Orchestrator.routing_mismatch` appears and task ends with `routing_mismatch`.
   - Environment requirements logged as `DecisionGate.requirements_resolved`, missing deps as `DecisionGate.requirements_missing`.
   - `kernel_required` marks intents requiring function calling (e.g. CODE_GENERATION, RESEARCH, KNOWLEDGE_SEARCH).
   - Missing kernel logs `DecisionGate.capability_required` → `DecisionGate.requirements_missing` → `Execution.execution_contract_violation`.

3. **Error standard (ErrorEnvelope):**
   - `error_code` is a stable error class (e.g. `routing_mismatch`, `execution_contract_violation`).
   - `error_details` contains details (e.g. `missing`, `expected_hash`, `actual_hash`, `stage`).
   - UI renders badge from `error_code` and details from `error_details` - no exception string parsing.

## Scenario: intent recognized, no tools available

If an intent is recognized but there are no matching tools/actions, the system **does not call the LLM**.
The request is routed to `UnsupportedAgent`, which returns a template response.

**Consequences in logs and process:**
- Trace includes `DecisionGate.route_to_agent` → `UnsupportedAgent.process_task`.
- No real LLM call (meta may be cleared to `None/None`).
- This signals missing tooling and should drive tool roadmap.

**Goal:** ensure the system does not “fake” an answer when tools are missing, and instead reports unsupported tasks clearly.

## Definition: tools as specialist knowledge

In this strategy, **tools** are treated as specialist knowledge that the LLM **does not have**:
- Tools provide up-to-date external/system knowledge (internet, time, system state).
- LLM answers only from its own knowledge; if unsure, it should admit uncertainty.
- If a tool is required but missing, the request goes to `UnsupportedAgent`.

**Logging impact:** `UnsupportedAgent` entries signal missing tools, not lack of model intelligence.

### Decision breakdown: LLM vs tool

**Simple rule:** anything that does not require a tool goes to the LLM.

**LLM (no tools):**
- General/static knowledge and definitions
- Explanations, summaries, inferences, paraphrases
- Content, code, descriptions, plans
- When no external data is required and model knowledge is sufficient

**Tool required:**
- “Here and now” data (current time, weather, news, web results)
- System state (files, processes, resources, logs, config)
- External interactions (APIs, web, integrations)
- Any task where results depend on fresh/local data

**Consistency rule:**
- If a tool is required but does not exist or does not match intent,
  the request ends as `UnsupportedAgent` and becomes a tooling candidate.

**Growth rule:** if a task does not require tools and goes to LLM, a learning process runs:
- log user need (what they wanted),
- identify shortcuts (how to do it faster next time),
- signals form a backlog for improvements or future tools.

Trace includes `DecisionGate.tool_requirement`, and learning entries are saved to
`data/learning/requests.jsonl`. Logs available via `GET /api/v1/learning/logs`
with optional filtering (`intent`, `success`, `tag`).

User feedback is stored in `data/feedback/feedback.jsonl` and available via
`GET /api/v1/feedback/logs`. Quality metrics are in `/api/v1/metrics`
(fields `feedback.up` and `feedback.down`).

Hidden prompts (approved prompt → response pairs) are aggregated from
`data/learning/hidden_prompts.jsonl` and exposed via
`GET /api/v1/learning/hidden-prompts`.

### Checklist: when to add a tool

- Does the answer require current data (time/state/system/internet)?
- Must the result be verifiable from an external source?
- Would the LLM have to guess/hallucinate without a tool?
- Are there repeated requests ending in `UnsupportedAgent`?

### Examples

- “What time is it?” → tool (system time)
- “Check queue status” → tool (system status)
- “Explain OAuth” → LLM (static knowledge)
- “Summarize this description” → LLM (user text analysis)

### Table: intent-to-tool mapping

| Intent / need | Required data | Tool required | If missing | Example |
| --- | --- | --- | --- | --- |
| Current time | System “now” | `time.now` | `UnsupportedAgent` | “What time is it?” |
| System state | Local resources, processes, logs | `system.status` | `UnsupportedAgent` | “Check queue status” |
| Internet data | External sources, current info | `web.search` | `UnsupportedAgent` | “Latest news?” |
| File ops | Workspace files | `fs.read` / `fs.list` | `UnsupportedAgent` | “Show config file” |
| Concept explanation | LLM general knowledge | none | LLM answers or admits no knowledge | “What is OAuth?” |
| Text summary | User text | none | LLM answers | “Summarize this description” |

### Current tools (skills)

| Skill (module) | Scope | Functions (examples) |
| --- | --- | --- |
| `AssistantSkill` (`assistant_skill.py`) | Time, weather, service status | `get_current_time`, `get_weather`, `check_services` |
| `BrowserSkill` (`browser_skill.py`) | Playwright E2E / browser | `visit_page`, `take_screenshot`, `get_html_content`, `click_element`, `fill_form`, `wait_for_element`, `close_browser` |
| `ChronoSkill` (`chrono_skill.py`) | Checkpoints & timelines | `create_checkpoint`, `restore_checkpoint`, `list_checkpoints`, `branch_timeline`, `merge_timeline` |
| `ComplexitySkill` (`complexity_skill.py`) | Task complexity estimates | `estimate_time`, `estimate_complexity`, `suggest_subtasks`, `flag_risks` |
| `ComposeSkill` (`compose_skill.py`) | Docker Compose / stacks | `create_environment`, `destroy_environment`, `check_service_health`, `list_environments` |
| `CoreSkill` (`core_skill.py`) | Venom code operations | `hot_patch`, `rollback`, `list_backups`, `restart_service`, `verify_syntax` |
| `DocsSkill` (`docs_skill.py`) | Documentation build | `generate_mkdocs_config`, `build_docs_site`, `serve_docs`, `check_docs_structure` |
| `FileSkill` (`file_skill.py`) | Workspace files | `write_file`, `read_file`, `list_files`, `file_exists` |
| `GitSkill` (`git_skill.py`) | Git / repo | `init_repo`, `checkout`, `get_status`, `get_diff`, `add_files`, `commit`, `push`, `pull`, `merge`, `reset` |
| `GithubSkill` (`github_skill.py`) | GitHub (public API) | `search_repos`, `get_readme`, `get_trending` |
| `GoogleCalendarSkill` (`google_calendar_skill.py`) | Calendar | `read_agenda`, `schedule_task` |
| `HuggingfaceSkill` (`huggingface_skill.py`) | Hugging Face | `search_models`, `get_model_card`, `search_datasets` |
| `InputSkill` (`input_skill.py`) | System input (mouse/keyboard) | `mouse_click`, `keyboard_type`, `keyboard_hotkey`, `get_mouse_position`, `take_screenshot` |
| `MediaSkill` (`media_skill.py`) | Graphics / assets | `generate_image`, `resize_image`, `list_assets` |
| `ParallelSkill` (`parallel_skill.py`) | Map-Reduce / parallelism | `map_reduce`, `parallel_execute`, `get_task_status` |
| `PlatformSkill` (`platform_skill.py`) | GitHub/Slack/Discord | `get_assigned_issues`, `create_pull_request`, `comment_on_issue`, `send_notification`, `get_configuration_status` |
| `RenderSkill` (`render_skill.py`) | UI / widgets / charts | `render_chart`, `render_table`, `render_dashboard_widget`, `render_markdown`, `render_mermaid_diagram`, `update_widget` |
| `ResearchSkill` (`research_skill.py`) | Knowledge graph ingestion | `digest_url`, `digest_file`, `digest_directory`, `get_knowledge_stats` |
| `ShellSkill` (`shell_skill.py`) | Shell commands | `run_shell` |
| `TestSkill` (`test_skill.py`) | Tests and lint | `run_pytest`, `run_linter` |
| `WebSearchSkill` (`web_skill.py`) | Web search & scraping | `search`, `scrape_text`, `search_and_scrape` |

2. **Performance:**
   - RequestTracer uses a Lock - operations are synchronous
   - Avoid high-frequency logging loops
   - Consider async logging if performance is critical

3. **Cleanup:**
   - Use `tracer.clear_old_traces(days=7)` to remove old traces
   - Consider adding it as a scheduled job in BackgroundScheduler

4. **Debugging:**
   - Check timeline in UI to see where a task “stuck”
   - LOST means no activity - check server logs

## Example scenarios

### Scenario 1: Success
```
User → submit_request
Orchestrator → start_processing
Orchestrator → classify_intent (RESEARCH)
ResearcherAgent → process_task
WebSkill → fetch_data
ResearcherAgent → generate_report
System → complete
```

### Scenario 2: Error
```
User → submit_request
Orchestrator → start_processing
Orchestrator → classify_intent (CODE_GENERATION)
CoderAgent → process_task
System → error (Connection timeout)
```

### Scenario 3: Lost (LOST)
```
User → submit_request
Orchestrator → start_processing
Orchestrator → classify_intent (RESEARCH)
ResearcherAgent → process_task
[5 minutes of inactivity]
Watchdog → timeout (Status: LOST)
```

## Troubleshooting

**Problem:** History does not load
- Ensure `request_tracer` is initialized in `main.py`
- Check server logs for init errors

**Problem:** Requests do not appear in history
- Ensure Orchestrator receives `request_tracer` in the constructor
- Check watchdog is running: `await tracer.start_watchdog()`

**Problem:** Missing steps in timeline
- Ensure components call `tracer.add_step()`
- Ensure `request_id` is passed correctly

**Problem:** Too many requests stored
- Use `tracer.clear_old_traces(days=N)` regularly
- Consider adding scheduled cleanup job

## Future extensions

- [ ] Export history to CSV/JSON
- [ ] Filter by intent/agent
- [ ] Performance statistics (avg time, success rate)
- [ ] Integration with BaseAgent (automatic logging)
- [ ] WebSocket real-time updates for history
- [ ] Dependency graph visualization
