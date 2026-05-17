# Coding Agent Task Template (Scoped Execution)

Use this template for coding-agent implementation tasks.

## Task Scope (fill before assigning)

- Goal:
- Source of truth (branch / PR / task doc):
- In-scope files/modules:
- Out-of-scope (explicit):
- Done definition (single sentence):

## Hard Constraints

1. Preflight before coding: confirm scope, files, env/tooling.
2. Avoid broad repository re-exploration after implementation starts.
3. If the same gate fails twice without code/environment changes, stop and report blocker.
4. Keep output compact: no raw full logs unless explicitly requested.
5. For OpenAI/Codex API/product questions, use Docs MCP first.
6. Prefer lightweight context artifact `test-results/agent-context/brief.json` before manual exploration.

## Mandatory Work Sequence

1. Preflight.
2. Implement minimal end-to-end slice.
3. Run targeted tests.
4. Run quality gates.
5. Publish concise handoff report.

## Mandatory Preflight Commands

```bash
set -euo pipefail
source .venv/bin/activate || true
python3 --version
node --version
npm --version
make ci-lite-preflight
```

If frontend scope exists, run:

```bash
npm --prefix web-next ci
```

## Mandatory Test Registration (when new tests are added)

1. Add tests under `tests/`.
2. Register in `config/testing/test_catalog.json` with:
   - `primary_lane: "new-code"`
   - `allowed_lanes: ["new-code", "ci-lite", "release"]`
3. Use neutral test filename/path (required for changed-code coverage selection), for example:
   - `tests/test_coding_run_service.py`
4. Do not use blocked slow-pattern tokens in test path/name:
   - `benchmark`
   - `integration`
5. If a new test was already added with a blocked token, rename it in the same PR.
6. Run checklist in order:
   - `make test-groups-sync`
   - `make test-groups-check`
   - `rg "tests/test_<new_name>\\.py" config/pytest-groups/sonar-new-code.txt`
   - `make check-new-code-coverage-diagnostics`

Interpretation rule:
1. If the test is missing in `config/pytest-groups/sonar-new-code.txt`, do not continue to full gate.
2. Fix naming/catalog/lane first, then rerun checklist.

## Completion Gate

Run and report:

```bash
make test-groups-check
make check-new-code-coverage-diagnostics
make pr-fast
```

Markdown-only exception:
1. If all changed files are `*.md`, `make pr-fast` may be skipped.

## Final Report Format (mandatory)

- Commands executed
- Pass/fail per command
- Changed-lines coverage (or `N/A` for markdown-only)
- Known blockers/risks and exact failure output
