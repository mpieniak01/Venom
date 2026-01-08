# Chat and Sessions (Current State)

This document describes how chat works, what data it collects, where it stores it, and how sessions are reset.

## Overview
- Chat works in `web-next` UI (Cockpit AI) and sends tasks to FastAPI backend.
- Conversation context is built on backend side based on session history and metadata.
- Conversation continuity is maintained within `session_id`.
- Backend restart forces new session (UI generates new `session_id`).

## Session ID (UI)
- `session_id` is generated on UI side and saved in `localStorage`:
  - `venom-session-id` (active session identifier),
  - `venom-next-build-id` (Next.js build),
  - `venom-backend-boot-id` (backend boot).
- UI compares `boot_id` with backend. When different, session is reset.

## Data Sources and Stores
### SessionStore (source of truth)
- File: `data/memory/session_store.json`
- Content: session history (`history`), optional `summary`, metadata.
- Used to build context for subsequent requests in the same session.

### StateManager (task state)
- File: `data/memory/state_dump.json`
- Content: `VenomTask` (content, result, logs, context_history).
- Session history in `context_history` is per-task (fallback).

### RequestTracer (RAM)
- API: `/api/v1/history/requests` and `/api/v1/history/requests/{id}`
- Content: prompt (shortened), status, steps, LLM metadata.
- Non-persistent (disappears after restart).

### Vector Memory (global)
- Persistent cross-session knowledge (e.g., LanceDB).
- Records: responses, summaries, lessons, facts.
- Cleaned only manually via "Clear global memory".

## How Chat Context is Built
1) UI sends `TaskRequest` with `session_id` and prompt content.
2) Backend builds context:
   - session metadata (ID, scope, language),
   - history from SessionStore (last N entries),
   - summary only when exists or explicitly requested,
   - vector memory only when conditions met (e.g., "remind", "earlier").
3) Model generates response, which is saved to:
   - SessionStore (session history),
   - StateManager (task result),
   - optionally to vector memory.

## Chat Routing Logic (why and what is called)
- Default rule: **if intent doesn't require tool and isn't forced, goes to LLM** (GENERAL_CHAT).
- Tools/skills are triggered only when:
  - intent requires tool (e.g., STATUS_REPORT, VERSION_CONTROL, RESEARCH), or
  - user forces it via slash command (`/git`, `/web`, etc.).
- This prevents wrong redirections (e.g., definition question as HELP_REQUEST) and keeps chat as conversation.

## Chat Work Modes (manual switch)
In chat UI there are three modes. This doesn't duplicate architecture – it's strategy control.

### 1) Direct (direct)
- **Routing:** no orchestrator, no tools, no planning.
- **Critical path:** UI → LLM → UI (shortest).
- **Logging:** RequestTracer with `session_id`, prompt and response (SimpleMode).
- **Use case:** reference for TTFT and typing.

### 2) Normal (standard)
- **Routing:** orchestrator + intent classification + standard logs.
- **Critical path:** UI → (intent/gating) → LLM → UI.
- **Logging:** full (history, steps, runtime).
- **Use case:** default system operation.

### 3) Complex (planning)
- **Routing:** forced intent `COMPLEX_PLANNING` → Architect → plan/steps.
- **Critical path:** UI → planning → LLM → UI.
- **Logging:** full + plan steps + decisions.
- **Use case:** multi-step and complex tasks.

## Request Details and Timings
"Request details" panel shows key critical path metrics:
- **UI timings:** `submit → history`, `TTFT (UI)`.
- **Backend timings:** `LLM.start` (tracer step), `first_token.elapsed_ms`, `streaming.first_chunk_ms`, `streaming.chunk_count`, `streaming.last_emit_ms`.
This allows assessing whether streaming works incrementally and where delays occur.

## Critical Path Pattern (UI → LLM → UI)
Goal: everything besides sending prompt and first chunk should work in background.
- **On path:** submit → TTFT → streaming/response.
- **In background:** trace, memory, panel refreshes, additional logs.

## Session Reset
- Session reset in UI creates new `session_id`.
- Session reset clears:
  - SessionStore for given session,
  - session entries in `state_dump.json`,
  - session memory in vector memory (if tagged with `session_id`).
- Global vector memory is not cleared automatically.

## Token Consequences
- Summary and vector memory increase prompt length only when enabled.
- By default summary is not generated automatically; created on request or with clear trigger.

## Current Approach
- Session reset after backend restart is intentional (boot_id). This behavior can be changed if need arises to maintain session after restart.
- Vector memory is global and persistent; not cleared per-session. In future, additional "session-only" mode or TTL rules may be introduced.
- Summary is generated only on request/trigger. Possible to switch to auto-summary for long sessions, at token cost.
- Memory retrieval is conditional (heuristics). In future this can be controlled configuratively or per-model.

## Where to Find Code
- Session UI: `web-next/lib/session.tsx`
- Chat UI: `web-next/components/cockpit/cockpit-home.tsx`
- Context building: `venom_core/core/orchestrator/session_handler.py`
- SessionStore: `venom_core/services/session_store.py`
