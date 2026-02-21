# THE ARCHITECT - Strategic Planning and Step Orchestration

## Role

Architect Agent is the planning layer for complex requests in Venom.
It converts one user goal into an executable `ExecutionPlan`, then orchestrates step-by-step execution through `TaskDispatcher`.

Core implementation: `venom_core/agents/architect.py`.

## Responsibilities

- Strategic decomposition of complex goals into concrete steps.
- Choosing the right executor per step.
- Enforcing step order through `depends_on`.
- Injecting dependency context between steps.
- Consolidating step outputs into a final execution summary.

## Executors and Intent Mapping

Architect plans with agent labels and maps them to dispatcher intents:

- `RESEARCHER` -> `RESEARCH`
- `CODER` -> `CODE_GENERATION`
- `LIBRARIAN` -> `KNOWLEDGE_SEARCH`
- `TOOLMAKER` -> `TOOL_CREATION`

If a step uses an unknown label, fallback intent is `CODE_GENERATION`.

## Runtime Flow

1. `IntentManager` classifies request as `COMPLEX_PLANNING`.
2. `TaskDispatcher` routes to `ArchitectAgent` (`agent_map["COMPLEX_PLANNING"]`).
3. `ArchitectAgent.process(input_text)`:
   - calls `create_plan(input_text)`,
   - then calls `execute_plan(plan)`.
4. Architect dispatches each step via `TaskDispatcher.dispatch(intent, content)`.
5. Final result is a combined execution report across all steps.

## Planning (`create_plan`)

`create_plan(user_goal)`:

1. Builds chat history with `PLANNING_PROMPT` + user goal.
2. Calls LLM via `_invoke_chat_with_fallbacks`.
3. Expects strict JSON with `steps[]`.
4. Removes accidental markdown code fences if returned.
5. Parses steps into:
   - `ExecutionStep.step_number`
   - `ExecutionStep.agent_type`
   - `ExecutionStep.instruction`
   - `ExecutionStep.depends_on`
6. Returns `ExecutionPlan(goal, steps, current_step=0)`.

### Planning Fallback Behavior

If JSON parsing or planning fails:
- Architect returns a minimal fallback plan with one step:
  - `step_number=1`
  - `agent_type="CODER"`
  - `instruction=user_goal`

This keeps execution alive but reduces task specialization.

## Execution (`execute_plan`)

`execute_plan(plan)` runs sequentially:

1. Validates `task_dispatcher` is set (`set_dispatcher` in initialization).
2. Iterates over steps in order.
3. For each step:
   - optionally broadcasts `PLAN_STEP_STARTED`,
   - builds step context,
   - dispatches to mapped intent,
   - stores step result (`step.result` and local `context_history`),
   - appends formatted summary section to final output,
   - optionally broadcasts `PLAN_STEP_COMPLETED`.
4. On step exception:
   - logs error,
   - appends error block to final summary,
   - continues with next steps.

### Dependency Context

When `depends_on` points to a completed step:
- Architect prepends previous step output as context.
- Dependency context is truncated to 1000 chars for safety.

## Event Broadcasting

When `event_broadcaster` is configured, Architect emits:

- `PLAN_CREATED`
- `PLAN_STEP_STARTED`
- `PLAN_STEP_COMPLETED`

This is optional and does not block core execution.

## Data Contract (ExecutionPlan)

Defined in `venom_core/core/models.py`:

- `ExecutionPlan.goal: str`
- `ExecutionPlan.steps: list[ExecutionStep]`
- `ExecutionPlan.current_step: int`

`ExecutionStep` fields:

- `step_number: int`
- `agent_type: str`
- `instruction: str`
- `depends_on: int | None`
- `result: str | None`

## Limitations

- Sequential execution only (no parallel step scheduler in Architect).
- No structural validation for cycles in `depends_on`.
- No automatic plan repair after partial step failures.
- Fallback single-step CODER plan may hide planning quality issues.

## Configuration

No dedicated `.env` flags are required for Architect itself.
Behavior depends on:

- LLM availability/configuration used by Kernel chat service.
- Dispatcher wiring (`TaskDispatcher` + `set_dispatcher`).
- Optional event broadcaster setup.

## Related Docs

- `docs/CHAT_SESSION.md` - routing modes and Complex path.
- `docs/THE_CODER.md` - code execution layer.
- `docs/THE_RESEARCHER.md` - research executor role.
- `docs/THE_INTEGRATOR.md` - issue-to-PR workflow with planning.
