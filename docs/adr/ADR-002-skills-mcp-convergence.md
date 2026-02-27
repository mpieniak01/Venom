# ADR-002: Skills/MCP Convergence via Local MCP-like Adapter

- Status: Accepted
- Date: 2026-02-27
- Deciders: Venom core maintainers

## Context
Venom currently has two parallel extension paths:
1. Native local skills (`venom_core/execution/skills/*`) loaded by `SkillManager`.
2. MCP-imported tools handled by `McpManagerSkill` + generated proxy wrappers.

This creates duplicated integration logic and different operational models for discovery, invocation, and governance.

Task 108 (Stage C) requires a PoC showing a converged direction without breaking the legacy path.

## Decision
Adopt an MCP-like adapter layer for local skills as an incremental convergence strategy.

For PoC:
1. Add `SkillMcpLikeAdapter` to expose local `@kernel_function` methods as MCP-like tools.
2. Add `GitSkillMcpAdapter` as the first concrete adapter.
3. Keep all existing legacy loading paths unchanged.

The adapter provides:
1. `list_tools()` with MCP-style tool metadata (`name`, `description`, `input_schema`).
2. `invoke_tool(name, arguments)` with required-argument validation and async/sync execution support.

## Consequences
Positive:
1. Shared contract for discovery/invocation across local skills and MCP proxies.
2. Low-risk migration path without switching runtime loading model in one step.
3. Reusable governance/observability hooks can target one tool contract.

Negative:
1. Temporary dual runtime remains (native plugins + MCP proxies + adapter).
2. Metadata mapping from SK annotations to JSON schema is simplified in PoC.
3. Additional adapter maintenance until full convergence.

## Migration Plan (ordered)
1. Git (PoC completed):
   - Use `GitSkillMcpAdapter` as reference implementation.
   - Validate command-level parity between native and MCP-like invocation.
2. File:
   - Introduce `FileSkillMcpAdapter`.
   - Add policy checks for path-jail and security parity.
3. Calendar:
   - Introduce `GoogleCalendarSkill` adapter with graceful-degradation behavior.
   - Align auth/credential error model with MCP-style tool errors.

## Alternatives considered
1. Full rewrite to MCP-only now:
   - Rejected due to high regression risk and broader operational impact.
2. Keep dual model without convergence:
   - Rejected because it preserves architectural duplication and inconsistent tooling contracts.

## Implementation notes
PoC code:
1. `venom_core/skills/mcp/skill_adapter.py`
2. `tests/test_mcp_skill_adapter_poc.py`
