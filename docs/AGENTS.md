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

## Default Test Command (Use First)

When test scope is unclear, start from this baseline:

```bash
source .venv/bin/activate
pytest -q
```

## Delivery Contract Without Timeboxes (Mandatory)

This section is the default execution mode for GitHub Coding Agent and takes priority over verbose exploration.

Wall-clock promises are forbidden for coding agents. Agent execution can be paused/resumed externally, so minute-based deadlines are not a reliable control mechanism.

Progress checkpoints:

1. preflight only (`git status`, target files, required env/tool check),
2. implement minimal end-to-end slice,
3. create first commit as soon as the first coherent slice is ready (WIP is allowed if tests are not green yet),
4. finish scope + targeted tests,
5. run `make pr-fast`, fix blockers, publish final report.

Hard stop rules:

1. No repeated repository exploration after implementation started.
2. Max one sub-agent invocation per phase (explore/implement/verify).
3. If two consecutive work iterations produce no code change and no test delta, stop and report blocker.
4. If the same gate fails twice without code/environment change, stop and report blocker.
5. Do not run non-required heavy checks before `make pr-fast` is green.

Commit discipline:

1. First commit must appear right after the first coherent slice is ready; do not batch everything at the end.
2. Prefer 1-3 focused commits over one final giant commit.
3. Do not postpone all commits until after long debugging loops.

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

Frontend bootstrap (required when frontend scope is touched):

```bash
npm --prefix web-next ci
```

Do not diagnose frontend test failures before `npm ci` is completed for `web-next`.

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
cd "$(git rev-parse --show-toplevel)"
make pr-fast
```

Pattern with log tail (still safe):

```bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
make pr-fast 2>&1 | tail -n 200
test ${PIPESTATUS[0]} -eq 0
```

Important:

1. `... | tail ...` returns tail's status by default, not the original command status.
2. Always use `set -o pipefail` and check `PIPESTATUS[0]` when command output is piped.

## Test Execution Playbook (Mandatory, Exact Order)

Run tests from repository root with active virtualenv:

```bash
cd "$(git rev-parse --show-toplevel)"
source .venv/bin/activate
```

1. Backend bootstrap (if environment is fresh/changed):

```bash
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-ci-lite.txt
```

2. Frontend bootstrap (mandatory when `web-next` scope is touched):

```bash
npm --prefix web-next ci
```

3. Targeted test pass before hard gate:
   - backend scope:

```bash
pytest -q tests/<path_or_file>.py
```

   - frontend scope:

```bash
make test-web-unit
```

   - when e2e scope is touched:

```bash
make test-web-e2e
```

4. Metadata/coverage diagnostics for changed Python code/tests:

```bash
make test-catalog-check
make test-groups-check
make check-new-code-coverage-diagnostics
```

5. Final mandatory gate (all non-markdown scopes):

```bash
make pr-fast
```

Default command profiles (use exactly one, based on scope):

Python-only scope:

```bash
source .venv/bin/activate
make test-ci-lite
make test-catalog-check
make test-groups-check
make check-new-code-coverage-diagnostics
make pr-fast
```

Frontend-only scope:

```bash
source .venv/bin/activate
npm --prefix web-next ci
make test-web-unit
make pr-fast
```

Mixed backend+frontend scope:

```bash
source .venv/bin/activate
npm --prefix web-next ci
make test-web-unit
make test-ci-lite
make test-catalog-check
make test-groups-check
make check-new-code-coverage-diagnostics
make pr-fast
```

Failure recovery for test metadata:

```bash
make test-catalog-sync
make test-groups-sync
make test-catalog-check
make test-groups-check
make check-new-code-coverage-diagnostics
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

## Two-Stage Quality Flow (GitHub Agent + Supervisor)

To keep GitHub Coding Agent sessions productive and deterministic, use two stages:

Stage A: Session Gate (GitHub Coding Agent, mandatory before handoff)

1. implement the requested scope (no endless re-exploration),
2. create at least one commit as soon as the first coherent slice is ready,
3. run targeted tests for touched modules,
4. run:
   - `make test-groups-check`
   - `make check-new-code-coverage-diagnostics`
5. publish a handoff report with blockers and exact failing commands.

Stage B: Merge Gate (Supervisor agent / final owner, mandatory before merge)

1. run full `make pr-fast`,
2. fix remaining gate failures,
3. merge only with green final gate status.

Rule:

1. Stage A does not replace Stage B.
2. Stage B remains the final repository-quality decision point.

## Documentation-Only Fast Path (Exception)

For markdown-only tasks, hard gates may be skipped to keep feedback fast.

Markdown-only scope (all changed files must match):
1. every changed file path ends with `.md` (any directory)

Rules:
1. If any changed file is outside markdown-only scope, full hard-gate policy is mandatory.
2. For markdown-only scope, skip:
   - `make pr-fast`
3. Completion report must include explicit note: "markdown-only change, hard gates skipped by policy".

## Completion Report Contract (Mandatory)

Every agent-generated completion summary (and PR description) must include:

1. list of executed validation commands,
2. pass/fail result for each command,
3. changed-lines coverage percentage from `make pr-fast` output (or `N/A` for markdown-only change sets where gate is skipped by policy),
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

## New-Test Registration Protocol (Mandatory)

When adding new tests for changed code, complete all items below in the same PR:

1. add test file under `tests/`,
2. register the test in `config/testing/test_catalog.json`,
3. for changed-code coverage use lanes:
   - `primary_lane: "new-code"`
   - `allowed_lanes: ["new-code", "ci-lite", "release"]`
4. run `make test-groups-sync`,
5. verify presence in `config/pytest-groups/sonar-new-code.txt`,
6. run `make check-new-code-coverage-diagnostics`.

Known pitfall (critical):

1. `make pr-fast` runs new-code selection with `NEW_CODE_EXCLUDE_SLOW_FASTLANE=1`.
2. Files matching slow patterns from `scripts/resolve_sonar_new_code_tests.py` may be excluded from coverage selection.
3. Current slow path patterns include `integration` and `benchmark`.
4. For tests that must participate in changed-code coverage, avoid slow-pattern tokens in the test path/name.

Required naming convention for new-code tests:

1. Use neutral names, e.g. `tests/test_coding_run_service.py`.
2. Avoid slow-pattern tokens in filename/path:
   - `benchmark`
   - `integration`
3. If a new test was already created with a blocked token, rename it in the same PR.

Minimal verification checklist (run in order):

```bash
make test-groups-sync
make test-groups-check
rg "tests/test_<new_name>\\.py" config/pytest-groups/sonar-new-code.txt
make check-new-code-coverage-diagnostics
make pr-fast
```

Interpretation rule:

1. If the test is missing in `sonar-new-code.txt`, do not continue to `make pr-fast`.
2. Fix catalog/lane/naming first, then rerun the checklist.

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
- Copilot coding-agent environment bootstrap: `.github/workflows/copilot-setup-steps.yml`.
- Anti-loop task template: `.github/coding-agent-task-template.md`.

## Architecture References

- System vision: `docs/VENOM_MASTER_VISION_V1.md`
- Backend architecture: `docs/BACKEND_ARCHITECTURE.md`
- Repository tree / directories map: `docs/TREE.md`

## Documentation Rule

- Functional catalog of Venom runtime agents belongs in `SYSTEM_AGENTS_CATALOG.md`.
- Implementation/process instructions for coding agents belong in this file.
