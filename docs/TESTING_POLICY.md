# Testing Policy

This document is the single source of truth for daily local testing, PR readiness checks, and release-oriented validation.

## Testing Ladder (from fastest to strictest)

### Level 1: Daily local work (every day)

Goal: very fast feedback while coding.

Run:

```bash
source .venv/bin/activate || true
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

Ensure hooks are installed for both `pre-commit` and `pre-push`:

```bash
make install-hooks
```

What it includes:

- changed-file scope detection against `origin/main` (or `PR_BASE_REF`)
- backend fast lane: compile check + CI-lite audit + changed-lines coverage gate
- frontend fast lane (only when `web-next/**` changed): lint + unit CI-lite

### Level 3: PR quality gates (mandatory before merge)

Goal: align with CI and Sonar expectations.

Required checks:

1. `pre-commit run --all-files`
2. `mypy venom_core`
3. `make check-new-code-coverage`

Coverage gate defaults:

- diff base: `origin/main`
- minimum changed-lines coverage: `80%`

Useful overrides:

```bash
NEW_CODE_CHANGED_LINES_MIN=80 make check-new-code-coverage
NEW_CODE_DIFF_BASE=origin/main make check-new-code-coverage
NEW_CODE_AUTO_INCLUDE_CHANGED=1 make check-new-code-coverage
```

New-code coverage run behavior:

- baseline test groups: `config/pytest-groups/ci-lite.txt` + `config/pytest-groups/sonar-new-code.txt`
- automatic include of changed tests/modules is enabled by default (`NEW_CODE_AUTO_INCLUDE_CHANGED=1`)
- changed test auto-include pattern: `tests/**/test_*.py`
- resolver script: `scripts/resolve_sonar_new_code_tests.py`
- if `ripgrep` (`rg`) is unavailable locally, resolver falls back to pure Python scanning
- CI backend-lite installs `ripgrep` for faster selection and deterministic logs

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

- CI Lite (fast lint + selected unit tests)
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
