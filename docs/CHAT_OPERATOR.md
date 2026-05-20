# chat_operator - Chat Operator Instruction

## Purpose

`chat_operator` is the operator-facing contract for Venom chat workflows. It keeps chat-specific behavior, state, tools, configuration, and lifecycle management out of the general operator manual.

Use this document when you need the operational answer to:

- which chat surfaces Venom exposes,
- which tools the chat can use,
- where chat/session configuration lives,
- how to manage runtime and session state,
- which `make` targets are the supported control surface.

## What the chat operator handles

| Surface or intent | What it does | Notes |
| --- | --- | --- |
| Cockpit chat | General assistant conversation in the UI | Default conversational surface |
| `GENERAL_CHAT` | Repo state, API scope, docs and scripts analysis | Routes to the LLM unless a tool is required |
| Memory actions | `recall()` and `memorize()` through `MemorySkill` | Used for user preferences and persistent facts |
| Calendar actions | `read_agenda()` and `schedule_task()` through `GoogleCalendarSkill` | Optional, not a primary chat topic |
| Session lifecycle | Session continuity, reset, and persistence | Uses `session_id` and session store files |
| Chat modes | `Direct`, `Normal`, `Complex` | See `CHAT_SESSION.md` for routing details |
| Session hygiene | Summary and memory retention rules | See `MEMORY_IN_CHAT.md` for the memory model |
| Repo analysis | `git status`, `git diff`, branch state, API contract scope | Default operator scenario |
| Docs and script remodeling | Documentation and script changes aligned with the contract | Preferred analysis/remodel workflow |

### What it does not own

- code generation and repo changes,
- research and web browsing,
- slash-tool routing outside chat,
- release or deployment policy.

Default chat scope:

1. git branch and repository status,
2. API contract scope,
3. documentation remodeling,
4. script remodeling,
5. only then auxiliary topics such as calendar.

Those concerns are routed through the dedicated tools, agents, and workflow docs.

## Canonical references

- [THE_CHAT.md](THE_CHAT.md)
- [CHAT_SESSION.md](CHAT_SESSION.md)
- [TOOLS_USAGE_GUIDE.md](TOOLS_USAGE_GUIDE.md)
- [CONFIG_PANEL.md](CONFIG_PANEL.md)
- [RUNTIME_PROFILES.md](RUNTIME_PROFILES.md)
- [MEMORY_IN_CHAT.md](MEMORY_IN_CHAT.md)

Use those documents for deeper technical detail. Use this document as the operator entrypoint.

## Where configuration lives

### Session and UI state

- `web-next/lib/session.tsx`
- `web-next/components/cockpit/cockpit-home.tsx`
- browser `localStorage` keys:
  - `venom-session-id`
  - `venom-next-build-id`
  - `venom-backend-boot-id`

### Backend session and memory state

- `venom_core/core/orchestrator/session_handler.py`
- `venom_core/services/session_store.py`
- `data/memory/session_store.json`
- `data/memory/state_dump.json`
- `data/memory/lancedb`

### Chat tools and runtime config

- `venom_core/memory/memory_skill.py`
- `venom_core/execution/skills/google_calendar_skill.py`
- `venom_core/services/config_manager.py`
- `venom_core/services/runtime_controller.py`
- `config/chat_operator/venom_operator_tool_profile.json`
- `config/chat_operator/agent_state_registry.json`
- `.env`
- `.env.dev`
- `config/env-history/`

### Relevant environment keys

- `AI_MODE`
- `LLM_LOCAL_ENDPOINT`
- `LLM_MODEL_NAME`
- `ENABLE_GOOGLE_CALENDAR`
- `GOOGLE_CALENDAR_CREDENTIALS_PATH`
- `GOOGLE_CALENDAR_TOKEN_PATH`
- `VENOM_CALENDAR_ID`
- `MEMORY_ROOT`

## How to manage chat runtime

The chat surface should be managed with explicit, repeatable `make` targets instead of ad-hoc shell commands.

### Runtime lifecycle

1. Start local-first chat runtime:
   ```bash
   make local-first-start MODEL=qwen2.5-coder:7b
   ```
2. Check runtime state:
   ```bash
   make local-first-status
   ```
3. Run the local Codex-backed chat lane:
   ```bash
   make local-first-codex MODEL=qwen2.5-coder:7b PROMPT='Powiedz tylko OK.'
   ```
4. Run repo-truth-first agent lane (injects real `git status`/`git diff` preflight into the prompt):
   ```bash
   make local-first-repo-truth-agent MODEL=qwen2.5-coder:7b PROMPT='Przeanalizuj stan repo i podaj kolejny krok.'
   ```
5. Unload model memory:
   ```bash
   make local-first-unload MODEL=qwen2.5-coder:7b
   ```
6. Stop local-first runtime:
   ```bash
   make local-first-stop
   ```

### Validation and probes

1. Feedback-model probe:
   ```bash
   make local-first-feedback-probe
   ```
2. Tool-flake matrix:
   ```bash
   make local-first-tool-flake-probe
   ```
3. Local chat truth/tool diagnostics:
   ```bash
   make local-first-chat-diagnostics
   ```
   - override matrix with `MODELS`, `CHANNELS`, `PROMPT_VARIANTS`, `IGNORE_RULES`
   - use `SHELL_ONLY=1` for a simple repo baseline without model calls
4. Repo-truth preflight probe (hard preflight with real `git status` before agent response):
   ```bash
   make local-first-repo-truth-preflight-probe MODEL=qwen2.5-coder:7b
   ```
5. Agent and prompt config validation:
   ```bash
   make local-first-agent-config-validate
   ```
6. Terminal contract probe (`VSCODE_AGENT`):
   ```bash
   make local-first-vscode-agent-probe
   ```
7. Utility-model settings probe (`chat.utilityModel` / `chat.utilitySmallModel`):
   ```bash
   make local-first-utility-models-probe
   ```
   - default contract source: `config/chat_operator/vscode_chat_models_contract.json`
   - optional local override: `make local-first-utility-models-probe SETTINGS_FILE=.vscode/settings.json`
8. Workspace-context probe (`AGENTS.md`, nested `AGENTS.md`, `#codebase`, local index metadata):
   ```bash
   make local-first-workspace-context-probe
   ```
   - default contract source: `config/chat_operator/vscode_workspace_context_contract.json`
   - optional local override: `make local-first-workspace-context-probe SETTINGS_FILE=.vscode/settings.json`
9. Decision gate (final model/routing contract):
   ```bash
   make local-first-decision-gate
   ```
   - default contract source: `config/chat_operator/decision_gate_contract.json`
   - optional override: `make local-first-decision-gate CONTRACT_FILE=...`
   - strict mode (fail when there is no exact repo-truth run): `make local-first-decision-gate STRICT_REPO_TRUTH=1`
10. Full agent contract probe:
   ```bash
   make local-first-full-agent-contract-probe
   ```
   - default contract source: `config/chat_operator/venom_full_agent_contract.json`
   - optional override: `make local-first-full-agent-contract-probe CONTRACT_FILE=...`
11. Full agent debug loop probe:
    ```bash
    make local-first-full-agent-debug-probe
    ```
    - default contract source: `config/chat_operator/venom_full_agent_debug_contract.json`
    - optional override: `make local-first-full-agent-debug-probe CONTRACT_FILE=... SETTINGS_FILE=...`
12. Full agent handoff probe:
    ```bash
    make local-first-full-agent-handoff-probe
    ```
    - default contract source: `config/chat_operator/venom_full_agent_handoff_contract.json`
    - optional override: `make local-first-full-agent-handoff-probe CONTRACT_FILE=...`
13. Full agent tool-usage probe:
    ```bash
    make local-first-full-agent-tool-probe
    ```
    - default contract source: `config/chat_operator/venom_full_agent_tool_contract.json`
    - optional override: `make local-first-full-agent-tool-probe CONTRACT_FILE=...`
14. Full agent gate:
    ```bash
    make local-first-full-agent-gate
    ```
    - aggregates full-agent persona, tool-usage, debug, and handoff probes
    - optional override: `make local-first-full-agent-gate PERSONA_REPORT=... TOOL_REPORT=... DEBUG_REPORT=... HANDOFF_REPORT=...`
15. PR237 env/index readiness probe:
    ```bash
    make local-first-env-index-readiness-probe
    ```
    - default contract source: `config/chat_operator/venom_agent_decision_contract.json`
16. PR237 agent decision evidence probe:
   ```bash
   make local-first-agent-decision-evidence-probe
   ```
   - validates evidence schema (`repo_truth`, `tools_used`, `decision`, `next_step`) from repo-truth-first lane
17. PR238G agent state registry probe:
   ```bash
   make local-first-agent-state-registry-probe
   ```
   - captures the canonical agent/environment state registry and live repo truth snapshot
18. PR237 policy enforcement probe:
   ```bash
   make local-first-policy-enforcement-probe
   ```
   - validates repo-level hook wiring and policy gate script for repo-truth workflow
19. PR237 final decision gate:
   ```bash
   make local-first-agent-decision-gate
   ```
   - aggregates env/index readiness, decision evidence, policy enforcement, and state registry probes
20. Chat operator docs drift audit:
   ```bash
   make chat-operator-docs-drift-audit
   ```
    - validates that operator docs only mention commands present in canonical `make help` and `make local-first-help`

### Shell profile management

If the local-first environment variables need to persist in the shell, manage them with:

1. `make local-first-profile-status`
2. `make local-first-profile-print`
3. `make local-first-profile-backup`
4. `make local-first-profile-restore`
5. `make local-first-profile-install`
6. `make local-first-profile-remove`

## Short Makefile cheat sheet

- `make local-first-start MODEL=qwen2.5-coder:7b` - start Ollama and preload the chosen model
- `make local-first-status` - check whether the local-first runtime is up
- `make local-first-codex MODEL=... PROMPT=...` - execute a local Codex prompt
- `make local-first-repo-truth-agent MODEL=... PROMPT=...` - run agent with mandatory repo-truth preflight context from terminal
- `make local-first-unload MODEL=...` - unload one model from memory
- `make local-first-stop` - stop the local-first runtime
- `make local-first-feedback-probe` - measure model behavior for feedback/review work
- `make local-first-tool-flake-probe` - run the tool-call stability matrix
- `make local-first-chat-diagnostics` - compare repo truthfulness and tool-use behavior
- `make local-first-repo-truth-preflight-probe MODEL=...` - enforce repo-truth preflight (`git status`/`git diff`) before agent output validation
- `make local-first-agent-config-validate` - validate agents, prompts, and instructions
- `make local-first-vscode-agent-probe` - verify terminal env contract for `VSCODE_AGENT`
- `make local-first-utility-models-probe` - validate utility-model split contract for chat settings (with optional `SETTINGS_FILE=...` override)
- `make local-first-workspace-context-probe` - validate workspace context contract (`AGENTS.md`, nested `AGENTS.md`, `#codebase`, local-index-first metadata)
- `make local-first-decision-gate` - validate final operator/utility model choices and main-window vs Agents-window routing
- `make local-first-decision-gate STRICT_REPO_TRUTH=1` - strict gate that fails when there are zero exact repo-truth model runs
- `make local-first-full-agent-contract-probe` - validate the Venom full-agent persona, tools, handoffs, and debug contract
- `make local-first-full-agent-debug-probe` - validate the Venom full-agent debug loop contract, debug views, and local logging setting
- `make local-first-full-agent-handoff-probe` - validate the Venom full-agent implementation handoff, worktree isolation, and return path
- `make local-first-full-agent-tool-probe` - validate the Venom full-agent tool-loop contract for repo truth, search, read, edit, terminal, and subagent usage
- `make local-first-full-agent-gate` - validate the final PR236 contract across persona, tools, debug, and handoff probes
- `make local-first-env-index-readiness-probe` - validate PR237 environment capability and repo index readiness for decision workflow
- `make local-first-agent-decision-evidence-probe` - validate PR237 decision evidence schema from repo-truth-first agent lane
- `make local-first-policy-enforcement-probe` - validate PR237 policy hook wiring and session-end enforcement script
- `make local-first-agent-decision-gate` - aggregate PR237 readiness, evidence, and policy probes into one PASS/FAIL gate

## Venom full agent

`Venom Full Agent` is the implementation persona for PR236.

Use it when you need a single agent that:

1. starts from repo truth,
2. analyzes code and diffs,
3. edits files with tool support,
4. can hand off to `Venom Release Guard` and `Venom Hard Gate Engineer`,
5. is debugged through Agent Debug Log and Chat Debug View.

Tool contract:

1. `search/codebase` and `search/usages` are the first-line tools for analysis.
2. `read` is required before claiming repository state.
3. `edit` is for the smallest safe change set, not speculative rewrites.
4. `terminal` is for real commands, tests, and git truth.
5. `runSubagent` is for bounded work only when the task can be split cleanly.
6. If a tool is unavailable, say so and fall back explicitly instead of inventing results.
7. start from repo truth before making changes.

Debug loop expectations:

1. Open Agent Debug Log for multi-step sessions.
2. Open Chat Debug View to inspect raw request/response payloads.
3. Keep `github.copilot.chat.agentDebugLog.fileLogging.enabled` enabled in workspace settings when you want persistent debug logs.
4. Use the VS Code commands `Show Agent Debug Logs` and `Developer: Show Chat Debug View` when you need to open those surfaces from the command palette.

Implementation handoff expectations:

1. Use local agent mode for planning until the task is specific enough.
2. Handoff to Copilot CLI in an isolated worktree for longer implementation runs.
3. Return to the main VS Code window for review and merge preparation.
4. Keep `Venom Release Guard` and `Venom Hard Gate Engineer` as the stabilization and final-gate paths.
5. Handoff steps: plan in main VS Code window, handoff to Copilot CLI worktree, implement in isolated worktree, review in main VS Code window.

The full-agent contract lives in:

- `.github/agents/venom-full-agent.agent.md`
- `docs_dev/_done/236_pr_pelny_agent_venom_vscode_debug_tools_dev.md`
- `docs/CHAT_OPERATOR.md`
- `docs/PL/CHAT_OPERATOR.md`

## Related docs

- EN operator manual: [OPERATOR_MANUAL.md](OPERATOR_MANUAL.md)
- PL operator manual: [PL/OPERATOR_MANUAL.md](PL/OPERATOR_MANUAL.md)
- EN chat internals: [THE_CHAT.md](THE_CHAT.md), [CHAT_SESSION.md](CHAT_SESSION.md)
- PL chat internals: [PL/THE_CHAT.md](PL/THE_CHAT.md), [PL/CHAT_SESSION.md](PL/CHAT_SESSION.md)
