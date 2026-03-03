# Coding Agent Task Template (Anti-Loop)

Use this template for any coding-agent implementation task.

## Task Scope (fill before assigning)

- Goal:
- In scope files/modules:
- Out of scope (explicit):
- Done definition (single sentence):

## Hard Constraints

1. Do not re-explore repository after implementation starts.
2. Maximum one sub-agent call per phase (`explore`, `implement`, `verify`).
3. First commit must be created within 30 minutes.
4. If no code change for 15 minutes, stop and report blocker.
5. If the same gate fails twice without code/environment changes, stop and report blocker.

## Mandatory Session Plan (1 hour)

1. `0-5 min`: preflight only.
2. `5-25 min`: minimal end-to-end implementation slice.
3. `<=30 min`: first commit (WIP allowed).
4. `30-50 min`: finish scope + targeted tests.
5. `50-60 min`: handoff report + final checks.

## Mandatory Preflight Commands

```bash
set -euo pipefail
source .venv/bin/activate || true
python3 --version
node --version
npm --version
npm --prefix web-next ci
make ci-lite-preflight
```

## Mandatory Test Registration (when new tests are added)

1. Add tests under `tests/`.
2. Register in `config/testing/test_catalog.json` with:
   - `primary_lane: "new-code"`
   - `allowed_lanes: ["new-code", "ci-lite", "release"]`
3. Run `make test-groups-sync`.
4. Verify test appears in `config/pytest-groups/sonar-new-code.txt`.
5. Run `make check-new-code-coverage-diagnostics`.

Pitfall:
- Avoid `benchmark` and `integration` in new test path/name when changed-code coverage selection is required (`NEW_CODE_EXCLUDE_SLOW_FASTLANE=1`).

## Handoff Gate (for GitHub Coding Agent)

Run and report status:

```bash
make test-groups-check
make check-new-code-coverage-diagnostics
```

Final merge gate is executed by supervisor/owner:

```bash
make pr-fast
```

## Final Report Format (mandatory)

- Commands executed
- Pass/fail per command
- Changed-lines coverage (or `N/A` for markdown-only)
- Known blockers/risks and exact failure output
