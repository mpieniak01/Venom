# API Contract Wave-2 PR Scope (Gap #7)

## Status
- `Draft` (2026-02-18)
- Scope owner: API contract stream (BE/FE)

## Context (official PR baseline)
1. #360 - Centralize API schemas and unify DI pattern across route handlers
2. #362 - API map dynamic contract and UI fixes
3. #375 - Close API contract stream: centralize schemas, explicit response models, BE/FE type alignment
4. #376 - Close scope 154-158 + Sonar fixes

Current state after these PRs:
1. `GET /api/v1/system/api-map` has explicit contract.
2. Memory contract moved from loose dict responses to explicit schemas for Wave-1/Wave-2 MVP.
3. Remaining Wave-2 work is focused on DI globals cleanup in selected routers and final hardening of loose response contracts.

## Goal of this PR
Close remaining Gap #7 scope without breaking API 1.x compatibility.

## In Scope
1. Remove remaining local dependency globals (`set_dependencies` + module-level mutable state) in Wave-2 candidate routers.
2. Remove remaining stable `response_model=dict[str, Any]` usage.
3. Keep OpenAPI and generated FE types aligned with backend contracts.
4. Provide formal closure evidence for contract stream (148/151 closure criteria).

## Out of Scope
1. API 2.0 redesign.
2. Runtime strategy redesign (covered by ADR stream).
3. Frontend redesign unrelated to API contract compatibility.

## Proposed implementation set
1. DI cleanup Wave-2 candidate routers:
- `venom_core/api/routes/calendar.py`
- `venom_core/api/routes/strategy.py`
- `venom_core/api/routes/queue.py`
- `venom_core/api/routes/feedback.py`
- `venom_core/api/routes/knowledge.py`

2. Response contract cleanup:
- Replace `response_model=dict[str, Any]` in `venom_core/api/routes/academy.py` with explicit schema in `venom_core/api/schemas/academy.py`.

3. OpenAPI/type sync:
- `make openapi-export`
- `make openapi-codegen-types`

4. New-code coverage hardening pack (added to scope):
- `venom_core/services/control_plane_compatibility.py`
- `venom_core/core/intent_embedding_router.py`
- `venom_core/learning/training_metrics_parser.py`
- `venom_core/infrastructure/gpu_habitat.py`
- `venom_core/api/routes/academy.py`
- `venom_core/core/provider_observability.py`
- `venom_core/simulation/persona_factory.py`
- `venom_core/services/control_plane.py`
- `venom_core/api/dependencies.py`
- `venom_core/api/routes/providers.py`
- `venom_core/core/routing_integration.py`
- `venom_core/services/profile_config.py`
- `venom_core/api/routes/workflow_control.py`
- `venom_core/utils/ollama_tuning.py`

## Acceptance Criteria
1. No `response_model=dict[str, Any]` in stable API routes targeted by this PR.
2. Selected Wave-2 routers no longer depend on local mutable globals for runtime dependencies.
3. OpenAPI includes explicit response schemas for all touched endpoints.
4. Existing API 1.x paths and request payloads remain backward compatible.
5. Hard gates pass:
- `make pr-fast`
- `make check-new-code-coverage`

## Validation Plan
1. Unit/integration tests for touched routers and schemas.
2. OpenAPI contract tests for updated endpoints.
3. Regression tests for dependency wiring and route startup.
4. Coverage-focused test additions for modules from the hardening pack.

## Risks and mitigations
1. Risk: dependency injection regression in startup wiring.
- Mitigation: add startup/router integration tests and backward-compatible getter wrappers.

2. Risk: FE type drift after schema changes.
- Mitigation: mandatory OpenAPI export + typegen in this PR and CI check.

## PR Description Template (GitHub)
Title:
- `Close Gap #7: API Contract Wave-2 (DI globals cleanup + explicit response schemas)`

Body:
- `Context`: continuation of #360, #362, #375, #376.
- `What changed`: DI Wave-2 cleanup in selected routers, academy response schema hardening, OpenAPI/type sync.
- `Compatibility`: API 1.x compatible, no endpoint path changes.
- `Validation`: include full command list, PASS/FAIL, changed-lines coverage, known skips/risks.

## Definition of Done
1. Gap #7 updated from partial to formally closed for Wave-2 target scope.
2. 148/151 contract stream closure criteria are auditable from merged PR artifacts.
3. No unresolved blocker from hard gates.
