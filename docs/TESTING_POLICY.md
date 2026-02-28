# Testing Policy

This document is the single source of truth for daily local testing, PR readiness checks, and release-oriented validation.

Security baseline and required controls are described in `docs/SECURITY_POLICY.md`.

## Testing Ladder (from fastest to strictest)

### Level 1: Daily local work (every day)

Goal: very fast feedback while coding.

Before adding new tests, verify required dependencies are available in the current environment and that they are allowed by the CI-lite dependency policy.

Run:

```bash
test -f .venv/bin/activate || { echo "Missing .venv/bin/activate. Create .venv first."; exit 1; }
source .venv/bin/activate
pytest -q
```

When frontend code changes, add:

```bash
npm --prefix web-next run lint
```

### Level 2: Branch ready for PR (mandatory before push)

Goal: verify the branch with lightweight PR-equivalent gates.

Run one command:

```bash
make pr-fast
```

Standalone architecture contract check (also executed inside `pr-fast`):

```bash
make architecture-drift-check
```

Standalone test-lane contract check (also executed inside `pr-fast`):

```bash
make test-lane-contracts-check
```

Canonical test taxonomy check (also executed inside `pr-fast`):

```bash
make test-catalog-check
```

Regenerate canonical catalog after larger test refactors/renames:

```bash
make test-catalog-sync
```

Ensure hooks are installed for both `pre-commit` and `pre-push`:

```bash
make install-hooks
```

What it includes:

- changed-file scope detection against `origin/main` (or `PR_BASE_REF`)
- backend fast lane: compile check + architecture drift guard + test-lane contracts guard + test-catalog guard + CI-lite audit + changed-lines coverage gate
- frontend fast lane (only when `web-next/**` changed): lint + unit CI-lite

Lane/group naming contract:

- `config/pytest-groups/fast.txt` is the canonical fast-scope backend list.
- `config/pytest-groups/light.txt` is a compatibility alias of `fast.txt` and should not be edited independently.

Test taxonomy model (canonical source: `config/testing/test_catalog.yaml`):

- `domain`: business/system scope (for example `academy`, `workflow`, `providers`, `runtime`)
- `test_type`: `unit`, `route_contract`, `service_contract`, `integration`, `perf`, `gate`
- `intent`: regression/contract/gate/security/performance
- `legacy_targeted`: historical PR-gate/coverage-wave style tests; must be domain-assigned

### Level 3: PR quality gates (mandatory before merge)

Goal: align with CI and Sonar expectations.

Minimum PR-ready set (copy 1:1):

```bash
pre-commit run --all-files
mypy venom_core
make check-new-code-coverage
```

Gate vs telemetry contract:

- `make check-new-code-coverage` is a merge-blocking gate.
- `make test-intelligence-report` is telemetry/trend and does not block merge.
- `make check-new-code-coverage-diagnostics` is optional manual diagnostics (non-gate helper output).

Coverage gate defaults:

- diff base: `origin/main`
- minimum changed-lines coverage: `80%`

Useful overrides:

```bash
NEW_CODE_CHANGED_LINES_MIN=80 make check-new-code-coverage
NEW_CODE_DIFF_BASE=origin/main make check-new-code-coverage
NEW_CODE_AUTO_INCLUDE_CHANGED=1 make check-new-code-coverage
```

Optional lightweight intelligence report (runtime impact + flaky candidates):

```bash
make test-intelligence-report
```

The report appends a trend snapshot to `test-results/sonar/test-intelligence-history.jsonl`.
Calibrated defaults (task 179 threshold calibration):
- `TEST_INTEL_SLOW_THRESHOLD=1.8` (ci-lite demotion candidate threshold)
- `TEST_INTEL_FAST_THRESHOLD=0.1` (new-code promotion candidate threshold)
- `TEST_INTEL_MIN_TESTS_PROMOTION=3` (avoid promotion noise for tiny files)

Manual override example:

```bash
TEST_INTEL_SLOW_THRESHOLD=2.0 TEST_INTEL_FAST_THRESHOLD=0.08 make test-intelligence-report
```

New-code coverage run behavior:

- baseline test groups: `config/pytest-groups/ci-lite.txt` + `config/pytest-groups/sonar-new-code.txt`
- automatic include of changed tests/modules is enabled by default (`NEW_CODE_AUTO_INCLUDE_CHANGED=1`)
- changed test auto-include pattern: `tests/**/test_*.py`
- resolver script: `scripts/resolve_sonar_new_code_tests.py`
- if `ripgrep` (`rg`) is unavailable locally, resolver falls back to pure Python scanning
- CI backend-lite installs `ripgrep` for faster selection and deterministic logs

Determinism contract (why this does not flake):

- `NEW_CODE_TIME_BUDGET_SEC=0` in CI: no time-based test list trimming.
- `config/coverage-file-floor.txt`: floor anchor tests are always included.
- `ripgrep` (`rg`) in CI: stable, fast resolver with readable logs.

How to verify coverage locally before push:

```bash
make check-new-code-coverage
```

Read these outputs:

- changed-lines verdict (`changed-lines coverage`)
- per-file floor verdict (`OK: coverage floors passed for ... files`)
- artifacts: `test-results/sonar/python-coverage.xml`, `test-results/sonar/python-junit.xml`

Quick triage hints (when gate fails):

- changed-lines coverage fail: add missing tests or enable `NEW_CODE_AUTO_INCLUDE_CHANGED=1`.
- coverage floors fail: missing anchor tests for a module listed in `config/coverage-file-floor.txt`.
- missing local `rg`: logs show Python fallback; install `ripgrep` when local/CI diverges.

Quality snapshot (reference, 2026-02-28):

- Sonar new-code coverage: `90.22%` (gate target: `>=80%`)
- Sonar overall coverage: `86.9%`
- Quality Gate: `Passed`

### Level 4: Release-oriented validation (when needed)

Goal: higher confidence for larger changes or pre-release checks.

Backend:

```bash
make pytest
```

`make pytest` runs backend groups in order: `heavy` -> `long` -> `fast`.

Frontend:

```bash
npm --prefix web-next run build
npm --prefix web-next run test:e2e
```

Sonar report bundle:

```bash
make sonar-reports
```

Artifacts:

- `test-results/sonar/python-coverage.xml`
- `test-results/sonar/python-junit.xml`
- `web-next/coverage/lcov.info` (optional/local artifact; temporarily not used by Sonar coverage gate)

Performance/latency scenarios:

- `docs/TESTING_CHAT_LATENCY.md`
- `npm --prefix web-next run test:perf`
- `pytest tests/perf/test_chat_pipeline.py -m performance`
- `./scripts/run-locust.sh`

## CI and Sonar Gates (reference)

Required PR gates:

- Architecture drift guard (`architecture-drift-guard` job in CI)
- CI Lite (fast lint + selected unit tests)
- Preprod readonly smoke lane (`make test-preprod-readonly-smoke`) in `backend-lite`
- SonarCloud (bugs, vulnerabilities, maintainability, duplication)
- Temporary exception: frontend `web-next/**` is excluded from Sonar coverage gate until UI stabilizes.

## Quality Criteria and Typical Failure Areas

These are the recurring quality risks in this repository and how we measure them.

### 1) Security issues

Typical failures:

- logging user-controlled data in backend routes
- regex patterns vulnerable to catastrophic backtracking
- incomplete Security Hotspot review in Sonar

Indicators:

- Sonar `Security Hotspots Reviewed`: target `100%` for PR scope
- Sonar `Vulnerabilities` and `Bugs`: no new `Critical/High`

### 2) Spaghetti / overly complex code paths

Typical failures:

- high cognitive complexity (`brain-overload`)
- long condition trees in route handlers and orchestration code
- hard-to-read control flow with mixed responsibilities

Indicators:

- Python complexity check: `ruff check venom_core --select C901`
- Sonar Cognitive Complexity rule threshold per function: `<= 15`
- no new `Critical` maintainability issues in PR scope

### 3) Excessive nesting

Typical failures:

- deeply nested blocks/callbacks reducing readability and testability

Indicators:

- Sonar code smell on deep nesting: no new open issue in PR scope
- prefer guard clauses / early returns during refactor

### 4) Weak new-code coverage

Typical failures:

- PR passes unit tests, but changed lines remain uncovered
- tests not included in the lightweight Sonar group

Indicators:

- local changed-lines gate: `make check-new-code-coverage`
- enforced minimum: `NEW_CODE_CHANGED_LINES_MIN=80` (default)
- recommended safety target before push: `>= 80%`
- Sonar new-code reference branch: `main` (`sonar.newCode.referenceBranch=main`)
- anomaly triage policy: `docs/QUALITY_FALSE_GREEN_TRIAGE.md`

### 5) Optional dependency drift in CI-lite

Typical failures:

- test imports optional package not present in CI-lite environment
- optional package missing turns into test `ERROR`/`FAILED` instead of explicit skip
- new test added but dependency behavior not documented

Indicators:

- optional library tests use `pytest.importorskip(...)` when dependency is not mandatory for CI-lite
- lightweight/system helper dependencies (for core parsing or test selection), e.g. `ripgrep`, are installed in CI-lite job
- backend-lite run shows explicit `skipped` (not import error) for optional-dependency tests

## Test Artifacts Policy

Do not commit test output artifacts.

Ignored by policy:

- `**/test-results/`
- `perf-artifacts/`
- `playwright-report/`
- Sonar local artifacts generated by `make sonar-reports`

## Definition of Done (Quality Gates)

A change is `Done` only when all gates below are green for the PR scope:

1. Fast local PR gate passed: `make pr-fast`
2. Static quality passed:
   - `pre-commit run --all-files`
   - `mypy venom_core`
   - `ruff check venom_core --select C901` (no remaining complexity violations in changed scope)
3. New-code coverage gate passed:
   - `make check-new-code-coverage`
   - changed-lines coverage `>= 80%`
4. SonarCloud PR gate passed:
   - no new `Critical/High` bugs/vulnerabilities
   - no new open maintainability blocker in PR scope
   - Security Hotspots in PR scope reviewed (`100%`)
5. If frontend changed:
   - `npm --prefix web-next run lint`
   - `npm --prefix web-next run test:unit:ci-lite`

## Optional Dependency Policy (CI-lite)

Use this rule for tests executed by `make check-new-code-coverage`:

1. Install in CI-lite when dependency is lightweight and broadly useful for fast gates.
2. Use `pytest.importorskip("package")` when dependency is heavy, environment-specific, or optional by design.
3. Never allow optional dependency absence to fail backend-lite with raw import errors.

Examples currently enforced:

- `tests/test_mcp_manager.py` uses `pytest.importorskip("mcp")`
- `tests/test_model_discovery.py` uses `pytest.importorskip("bs4")` in scraping-specific path
- backend-lite job installs `ripgrep` for `scripts/resolve_sonar_new_code_tests.py`
