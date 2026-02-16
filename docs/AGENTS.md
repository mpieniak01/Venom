# Coding Agents Guidelines (EN)

This file contains **instructions for coding agents** working in this repository.

If you are looking for the list of Venom system agents, use:
- [SYSTEM_AGENTS_CATALOG.md](SYSTEM_AGENTS_CATALOG.md)

## Core Rules

- Keep changes small, testable, and easy to review.
- Maintain typing quality (`mypy venom_core` should pass).
- Keep security checks green (Sonar/Snyk findings should be addressed, not ignored).
- Avoid dead code and placeholder branches.
- Make error paths explicit and covered by tests where practical.

## Hard Gate Policy (Mandatory)

Coding agents must not finish a task with red quality gates.

Required gate sequence before completion:

1. `make pr-fast`
2. `make check-new-code-coverage`

If any gate fails:

1. fix the issues,
2. rerun both commands,
3. repeat until both are green, unless there is a confirmed environment blocker.

A "partial done" status with failing gates is not allowed in this repository policy.

Environment blocker path:

1. set `HARD_GATE_ENV_BLOCKER=1` for the hard-gate hook execution,
2. include blocker details and impact in PR risks/limitations section.

## Documentation-Only Fast Path (Exception)

For documentation-only tasks, hard gates may be skipped to keep feedback fast.

Doc-only scope (all changed files must match):
1. `docs/**`
2. `docs_dev/**`
3. `README.md`
4. `README_PL.md`
5. other root `*.md` files

Rules:
1. If any changed file is outside doc-only scope, full hard-gate policy is mandatory.
2. For doc-only scope, skip:
   - `make pr-fast`
   - `make check-new-code-coverage`
3. Completion report must include explicit note: "doc-only change, hard gates skipped by policy".

## Completion Report Contract (Mandatory)

Every agent-generated completion summary (and PR description) must include:

1. list of executed validation commands,
2. pass/fail result for each command,
3. changed-lines coverage percentage from `make check-new-code-coverage`,
4. known skips/risks with explicit justification.

Use `.github/pull_request_template.md` as the report format baseline.

## Required Validation Before PR

- Run fast checks first (lint + targeted tests).
- Run relevant `pytest` groups for touched modules.
- Confirm no new critical/high security findings.

## User-Facing Messages i18n Rule (Mandatory)

- Any user-facing message (UI label, button, toast, modal, validation error, API error shown in UI, empty-state text) must be implemented via translation keys, not hardcoded strings.
- For new or changed user-facing messages, add/update translations in all supported locales: `pl`, `en`, `de`.
- Keep one key namespace and parity across locale files (no missing keys in one language).
- Do not merge changes with mixed-language UI caused by fallback hardcoded text.

## CI Stack Awareness Rule

- Before adding/updating tests for CI-lite, verify which dependencies and tools are available in the CI-lite stack.
- Use `requirements-ci-lite.txt`, `config/pytest-groups/ci-lite.txt`, and `scripts/audit_lite_deps.py` as the source of truth.
- If a test needs an optional dependency that is not guaranteed in CI-lite, use `pytest.importorskip(...)` or move that test out of the lite lane.

## Quality and Security Toolchain (Project Standard)

- **SonarCloud (PR gate):** mandatory pull request analysis for bugs, vulnerabilities, code smells, duplications, and maintainability.
- **Snyk (periodic scan):** recurring dependency and container security scans for newly disclosed CVEs.
- **CI Lite:** fast PR checks (lint + selected unit tests).
- **pre-commit:** local hooks expected before push.
- **Local static checks:** `ruff`, `mypy venom_core`.
- **Local tests:** `pytest` (targeted suites at minimum for changed modules).

Recommended local command sequence:

```bash
pre-commit run --all-files
ruff check . --fix
ruff format .
mypy venom_core
pytest -q
```

## Canonical Reference

- Source of truth for quality/security gates: `README.md` section **"Quality and Security Gates"**.
- Branch protection runbook for required checks: `.github/BRANCH_PROTECTION.md`.
- Coding-agent hook config: `.github/hooks/hard-gate.json`.
- Access management runbook: `.github/CODING_AGENT_ACCESS_MANAGEMENT.md`.
- MCP usage policy: `.github/CODING_AGENT_MCP_POLICY.md`.
- Custom agent profiles: `.github/agents/`.

## Architecture References

- System vision: `docs/VENOM_MASTER_VISION_V1.md`
- Backend architecture: `docs/BACKEND_ARCHITECTURE.md`
- Repository tree / directories map: `docs/TREE.md`

## Documentation Rule

- Functional catalog of Venom runtime agents belongs in `SYSTEM_AGENTS_CATALOG.md`.
- Implementation/process instructions for coding agents belong in this file.
