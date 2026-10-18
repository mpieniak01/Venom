# Release identity and Sonar analysis

## Release 1.10.0 preparation

The application release is synchronized in `pyproject.toml`, `venom_core/version.py`,
`web-next/package.json`, the lockfile root and Docker build defaults. The core
FastAPI/OpenAPI version uses `APP_VERSION`; the audio daemon has a separate service
version. Frontend build metadata continues to derive its version from package.json.
CI reads the release from pyproject.toml, checks frontend agreement and passes
`sonar.projectVersion` to both scanner modes. Use a release version, never a build
number. Historical README release sections retain their original versions.

The effective main new-code definition in the 18 October snapshot was
`previous_version`, baseline 1.5.1 (22 February), not merely the last commit.
A version event changes the future baseline; it does not repair or close existing
findings. Retain the pre-release full report and compare all-code findings after
publishing, as well as the new-code gate. This change does not edit the server's
baseline, quality gate, issue statuses or branch protection.

## Two analysis methods

SonarCloud Automatic Analysis ignores `sonar-project.properties`. It reads supported
settings from `.sonarcloud.properties`. The additional file supplies only encoding,
Python version and CPD exclusions; it does not reduce security/issue scan scope.
Translation dictionaries intentionally repeat language keys and object shapes.
They and tests are excluded from copy/paste metrics, not rewritten to defeat CPD.
CI retains its existing source/coverage policy and locale/test CPD exclusions.
There are no new rule suppressions or lowered thresholds.

Automatic Analysis and CI analysis must not run concurrently for this project.
Before enabling the CI scanner for this release, verify the cloud Analysis Method
setting and disable Automatic Analysis through the authorized project administrator.
The repository change alone does not switch that setting. Automatic Analysis does
not support coverage import and does not list projectVersion among its supported
file settings; no unsupported version property is added to its configuration.

Sources: [Automatic analysis](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/automatic-analysis),
[Project version parameter](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/analysis-parameters/parameters-not-settable-in-ui).

## Bounded triage of the 18 October main snapshot

Baseline main: `4b08cad82c4992d78fbe7da05d791c7ee76c28fc`.
Analysis: `b9333ca3-3d15-4393-b6fe-f3393a675c02`.
Gate ERROR: reliability C, security E, duplication 6.83% (limit 3%).
All open issues: 1130; in the previous-version period: 775.
Full raw evidence and issue keys are retained in the local Sonar triage report.

### Reliability fixes in this branch

- S7502 startup: keep the task alive and await loading before unloading at shutdown.
  Model loading uses a worker thread; cancelling its coroutine would not stop that
  thread. Cleanup also runs when the application context raises.
- S7502 restart: keep a strong task reference until completion, release it with a
  done callback and report exec failures instead of losing task exceptions.
- S7493 replay: read the WAV in a worker thread, then upload bytes, avoiding a
  synchronous file open/read in the event loop.

Tests use local stubs and temporary files; they do not load models or move a robot.

### Security blockers: reviewed context, not server-side resolution

| Issue key | Entry point / sink | Local assessment |
| --- | --- | --- |
| AaFN9X88CiUwZk3hXg33 | direct ingest CLI / normalized WAV output | Explicit operator-selected local output path; no HTTP input in this entrypoint. Arbitrary output is part of the CLI contract. Do not pass untrusted generated paths. Pending security review. |
| AaFN9YEbCiUwZk3hXg5N | coverage CLI / subprocess argument list | pytest executable is an explicit local tooling option. No shell evaluation. Actual subprocess regression verifies shell metacharacters remain literal. This does not make arbitrary executable selection safe for untrusted callers. Pending security review. |
| AaFN9X6aCiUwZk3hXg3i | dead-code CLI / vulture argument list | Same local executable trust boundary; no HTTP/LLM invocation found in runtime consumers. Literal-argument regression added. Pending security review. |
| AaFN9YJXCiUwZk3hXg6S | Sonar group updater / group file write | Output GROUP_PATH is a module constant; argv catalog is a separate input. Reported source is existing file content, not a destination path. Outside current new-code period; pending security review. |

The scanner labels these sources as HTTP/LLM input, but inspected entrypoints use
argparse or a fixed destination. No broad script exclusion or fake sanitization is
added. These issues remain OPEN in Sonar; a maintainer must confirm disposition
against the full flow before marking any false positive. The other security
findings, historic frontend promises, and broad maintainability debt remain a
separate backlog. This bounded change does not claim the cloud gate is green.

## Acceptance

Run targeted runtime, release identity and literal-subprocess tests; catalog/group
checks; `make pr-fast`; typing and CI-lite checks required by repository guidance.
After authorized publication, obtain a fresh cloud report for the final SHA.
Confirm dictionaries disappear only from CPD metrics, issue scope remains intact,
version event is correct, and compare total security findings with the saved report.
Local tests are not a substitute for that cloud acceptance.


## Local acceptance recorded 18 October 2026

Implementation under test: `6db26f40b3d0a0737b342efa1d861ac490274070`.
The following checks completed with exit status 0:

| Command | Result |
| --- | --- |
| `pytest -q tests/test_gemma4_audio_runtime_main.py tests/test_main_internal_helpers.py` | 143 passed; 2 existing dependency deprecation warnings |
| `pytest -q tests/test_dead_code_audit.py tests/test_update_sonar_scope_group.py` | 12 passed |
| `npm --prefix web-next ci --ignore-scripts --no-audit --no-fund` | 601 packages installed from lockfile; no audit request |
| `make test-catalog-check test-groups-check` | Catalog 504/504; groups synchronized |
| `make pr-fast VENV=/home/ubuntu/.venvs/venom266-sec-ci-a` | PASS; 97.1% changed-lines coverage; 14 file floors; frontend lint and 172 UI tests passed |
| `make test-ci-lite VENV=/home/ubuntu/.venvs/venom266-sec-ci-a` | PASS |
| `mypy venom_core` | PASS |
| `make check-new-code-coverage-diagnostics VENV=/home/ubuntu/.venvs/venom266-sec-ci-a` | PASS |
| `make test-web-unit` | PASS |

No additional model qualification, Snyk/npm rescan, operator deployment or cloud
Sonar scan was performed in this slice. Dependency versions are unchanged from
266; the application version alone changes package metadata. Existing vendor
findings and the CI boolean.py alias warning remain documented in the 266 audit.
Final documentation-only changes do not alter the tested implementation.

## Current PR stack and release order

The release is reviewed through three open PRs in two repositories. Local task
266 is represented by core PR #540; it is not a GitHub PR number.

| PR | Head branch | Review base | Scope |
| --- | --- | --- | --- |
| [Core #540](https://github.com/mpieniak01/Venom/pull/540) | `codex/266-maf-runtime-profiles` | `main` | Dependency profiles, pins, security qualification and MAF migration |
| [Rider module #24](https://github.com/mpieniak01/venom-module-rider/pull/24) | `codex/266-maf-tool-contract` | `main` in the module repository | First-party Venom tool contracts |
| [Core #541](https://github.com/mpieniak01/Venom/pull/541) | `codex/sonar-gate-1-10` | `codex/266-maf-runtime-profiles` | Release identity 1.10.0, Sonar configuration and bounded reliability fixes |

Before accepting #541, synchronize its branch with the final accepted HEAD of
#540 and run fresh checks for that combined candidate. A green child PR result
from an earlier parent revision does not qualify later changes or resolve a red
security gate on #540. Keep the two core PRs separate so their effective scopes
and unresolved findings remain reviewable.

After all release blockers are resolved and merging is authorized:

1. Merge core #540 into `main`. A merge commit preserves the ancestry of the
   stacked branch and makes the following review transition straightforward.
2. Merge Rider module #24 after its core contract exists. Do not deploy the module
   alone against the old core.
3. Retarget core #541 to `main`, inspect the effective diff and obtain fresh checks
   before merging it. If #540 is squash-merged, transplant only the Sonar follow-up
   commits onto the new `main` so the full 266 diff is not republished.

Complete remote CI/review and inspect a fresh Sonar result for the final candidate
before declaring the release accepted. Deploy the compatible final core/module
pair together, then run operator smoke tests. Preserve the old checkout until
acceptance; this document records the review sequence, not authorization or
evidence of a merge/deployment.
