# PR: 201D - Global Policy Gate at Orchestrator Level

## Goal
Close the governance gap by introducing a single central policy/autonomy checkpoint for the orchestrator execution path and removing legacy submit-level compatibility checks.

## Scope

### Backend
- Introduced central runtime gate: global_pre_execution.
- Removed submit-level `before_provider` compatibility gate so runtime enforcement has a single source of truth.
- Extended policy context with risk dimensions: desktop, fileops, shell, network.
- Standardized deny payload across policy/autonomy: reason_code, user_message, technical_context, remediation_hint.
- Standardized audit event for global gate block: policy.blocked.global_pre_execution.
- Extended task response schema with remediation_hint.

### Frontend
- Added new Permissions tab under /config.
- Added Permissions and Autonomy panel with:
  - current autonomy level,
  - permission matrix,
  - level change action,
  - one-click grant for analysis level,
  - autonomy.* events from the same audit stream.
- Aligned panel styling with Venom visual language and neighboring Audit section.

### Documentation
- Updated 201D status document to in_review with done/pending checklist.
- Updated project docs in PL/EN to reflect that orchestrator-wide global pre-execution gate is implemented.

## Validation
- make pr-fast: PASS
- make check-new-code-coverage: PASS
- targeted regression test: PASS

## Risks / Follow-up
- Review should focus on whether any downstream consumers still assume legacy `before_provider` audit semantics.
- Operational follow-up may still extract the new KPI block into a separate SRE-facing view if `/config` is not sufficient.

## Reviewer Checklist
- [ ] deny contract consistency across route/skill/orchestrator.
- [ ] runtime-only policy architecture is reflected consistently across code and docs.
- [ ] Permissions UI correctly reads and presents autonomy.* events.
- [ ] policy observability KPI payload is stable enough for dashboard consumers.
