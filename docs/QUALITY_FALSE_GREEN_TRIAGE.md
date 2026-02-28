# False-Green Triage Policy (New-Code Coverage)

## Goal
Prevent "green but risky" PR outcomes where gates pass while real regression risk remains.

## Scope
This policy applies to backend PRs using:
- `make pr-fast`
- `make check-new-code-coverage`
- Sonar new-code quality gate

## Primary false-green signals
1. Coverage gate reports `No coverable changed lines found (after exclusions).`
2. Significant config/runtime changes with minimal or zero test delta.
3. New tests only exercise happy-path without edge/error branches.
4. Group drift: tests moved between `ci-lite` and `sonar-new-code` without rationale.

## Triage workflow
1. Capture gate context:
   - `NEW_CODE_DIFF_BASE`
   - changed files list
   - selected tests list from coverage gate output
2. Classify anomaly:
   - `DIFF_SCOPE_MISMATCH`: changed files not mapped into coverable Python scope.
   - `TEST_SELECTION_GAP`: relevant tests missing from selected set.
   - `BRANCH_GAP`: line coverage exists, branch/error paths missing.
3. Apply mitigation:
   - add focused lightweight tests for missing branches/errors,
   - add/adjust lane assignment (`config/testing/lane_assignments.yaml`),
   - update `config/pytest-groups/sonar-new-code.txt` when systematic gap is found.
4. Re-run:
   - `make check-new-code-coverage`
   - `make pr-fast`
5. Record outcome in PR notes if anomaly was present.

## Mandatory escalation triggers
Escalate before merge when any trigger occurs:
1. Repeated `No coverable changed lines found` for code-touching backend PR.
2. Critical module change (`venom_core/core`, `venom_core/api/routes`, `venom_core/execution`) without meaningful test delta.
3. Lane contract violation found by `make test-lane-contracts-check`.

## Ownership
- Primary owner: backend platform/quality reviewers.
- Every PR author is responsible for anomaly triage when triggers occur.
