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
- Before running Python tooling, activate the repository virtualenv with `source .venv/bin/activate`.

## Quick Bootstrap (Package Install)

Use this exact sequence when environment state is unknown:

```bash
test -f .venv/bin/activate || python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-ci-lite.txt
```

Optional stack-specific dependencies:

```bash
python -m pip install -r requirements-extras-onnx.txt
```

Do not rely on ad-hoc one-off `pip install ...` without mapping it to the proper repository requirements file.

## Environment Variables (Reliable Loading)

If tests depend on `.env.dev`, load variables explicitly:

```bash
set -a
source .env.dev
set +a
```

For preprod smoke checks, prefer project make targets (they set required env contract), e.g.:

```bash
make test-preprod-readonly-smoke
```

## Shell Safety for Gates (Mandatory)

To avoid false-green reports:

1. never chain `cd` and `make` using `&` (use `&&`),
2. never infer gate status from truncated log output only,
3. when using pipelines (`| tail`), enable `pipefail` and validate `PIPESTATUS[0]`.

Recommended pattern:

```bash
set -euo pipefail
cd /home/runner/work/Venom/Venom
make pr-fast
```

Pattern with log tail (still safe):

```bash
set -euo pipefail
cd /home/runner/work/Venom/Venom
make pr-fast 2>&1 | tail -n 200
test ${PIPESTATUS[0]} -eq 0
```

## Hard Gate Policy (Mandatory)

Coding agents must not finish a task with red quality gates.

Required gate sequence before completion:

1. `make pr-fast`

Note: `make pr-fast` runs the new-code coverage gate internally. The standalone
`make check-new-code-coverage` command remains available for diagnostics/manual checks.

If any gate fails:

1. fix the issues,
2. rerun the gate,
3. repeat until green, unless there is a confirmed environment blocker.

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
3. Completion report must include explicit note: "doc-only change, hard gates skipped by policy".

## Completion Report Contract (Mandatory)

Every agent-generated completion summary (and PR description) must include:

1. list of executed validation commands,
2. pass/fail result for each command,
3. changed-lines coverage percentage from `make pr-fast` output,
4. known skips/risks with explicit justification.

Use `.github/pull_request_template.md` as the report format baseline.

## Required Validation Before PR

- Run fast checks first (lint + targeted tests).
- Run relevant `pytest` groups for touched modules.
- Confirm no new critical/high security findings.

## Coverage Gate: Why "Tests Passed" Can Still Fail

`make pr-fast` enforces changed-lines coverage against diff (`origin/main` by default), not only raw test pass rate.

If gate fails after adding tests:

1. run `make check-new-code-coverage-diagnostics`,
2. verify test catalog/groups consistency:
   - `make test-catalog-check`
   - `make test-groups-check`
3. sync when needed:
   - `make test-catalog-sync`
   - `make test-groups-sync`

`check-file-coverage-floor` failures are blocking. Do not classify as "pre-existing" without explicit reproduction on clean `origin/main`.

Coverage-floor triage (required, minimal):

1. run full `make pr-fast` (no `grep/head`-only decision path),
2. confirm threshold in `config/coverage-file-floor.txt`,
3. reproduce on clean `origin/main`,
4. if `origin/main` passes, treat current PR diff as regression and fix it.

Anti-patterns:

1. `git stash && make ... | grep ... | head ...` as evidence,
2. "pre-existing issue" claim without clean-main reproduction.

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
