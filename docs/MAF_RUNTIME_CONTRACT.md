# Venom runtime contract and MAF migration (266)

Status: implementation in progress. This document describes the migrated boundary;
it is not a release qualification or a declaration that all consumers are migrated.

## Ownership

`execution.agent_contracts` owns Venom conversation messages/history, mutable
completion settings and tool declarations. `execution.maf_runtime` uses the released
Microsoft Agent Framework Chat Completions provider. It contains no SK import or
fallback. `KernelBuilder` remains the public factory name so consumers need not
change their constructor contract. It now creates the small named service/tool
registry `AgentRuntime`; it does not emulate the complete Kernel SDK.

Existing agent methods keep their `process`, `process_with_params` and chat service
entry points. Aliases in migrated consumers are source migration aids. They are
Venom types, not instances of old SK classes. Extensions must import Venom contracts;
importing third-party SK types is not a supported compatibility promise.

## Model services and history

- Named service lookup remains available. `default` selects the first registered
  service if no explicitly named default exists; an unknown explicit name fails.
- Direct model completion does not construct a MAF agent or tool planner.
- A tool-enabled request uses MAF's native function loop. Native function call and
  result identities are kept in caller-owned history for the next model turn.
- Callers append the final assistant response. The runtime appends only intermediate
  tool messages; it does not execute a tool again while replaying history.
- Streaming emits existing text chunk lists. Cancellation and provider errors
  propagate; they are not converted to successful empty messages.
- The service owns and closes its AsyncOpenAI client, including internally created
  clients. The runtime closes its registered services on shutdown.
- Local provider token aliases are normalized to the existing Chat Completions
  `max_tokens` wire field using the SDK's public `extra_body` option. Nonstandard
  sampling options use that same public extension mechanism. Generation options
  cannot replace model routing, messages, tools or streaming configuration.

Gemini uses Google's official OpenAI-compatible Chat Completions endpoint. Optional
calendar and grounding capabilities remain separate skills. No paid API request is
required for offline contract tests.

## Tools and permissions

Use `tool_function` from `venom_core.execution.agent_contracts`. It preserves Python
method binding/signatures; the registry constructs native MAF FunctionTools from
bound callables. Generated MCP tools use this contract as well. The loader accepts
both the canonical decorator and its historical local alias `kernel_function`,
including asynchronous methods. Old generated files importing SK require migration.

Tools are filtered by plugin/function allow/exclude lists before being advertised.
Permissions are checked again at execution. A denial does not call the underlying
method. Existing action-specific enforcement inside skills remains in force.
Unknown function calls terminate rather than selecting another callable. MAF tool
limits are finite (5 rounds, 20 calls, 30 s best-effort budget); these SDK limits are
not a hard deadline for arbitrary blocking user code. Invocation is sequential and
exception details are not exposed to the model.

## Product routes retained

The cockpit still offers `direct`, `normal`, `complex` (see cockpit-chat-send and
execution_mode_planner). Direct uses the simple chat path, normal keeps orchestration,
and complex requests COMPLEX_PLANNING. Migration must not insert a planner/model
into direct or duplicate the shared template-response routing. End-to-end route and
performance qualification is a separate required gate; unit fixture transports do
not qualify a model or physical Rider-Pi.

## Validation boundary

`tests/test_maf_runtime.py` runs released MAF/OpenAI SDKs against deterministic HTTP
fixtures. Existing factory, agent, dispatcher, intent, history and skill tests are
migrated with each component. Clean Light/CI installation and lock integrity are
reported separately from actual inference, hardware and Docker qualification.
