# Split release 1.10.0: identity and Sonar acceptance

## Current release scope

This package prepares the 1.10.0 identity for the split Light/API release. The
application uses MAF with the active Light, CI and build dependency policy from
package B. Package A supplies the accepted Node/frontend dependency graph. Full,
Full-CI, ONNX CPU/extras, GPU engine and Academy profiles remain deferred as
specified in [dependency profiles](DEPENDENCY_PROFILES.md). This is not a full
runtime release or a new qualification of those environments.

Package D changes release identity and Sonar metadata only. Python packaging,
`venom_core/version.py`, API/OpenAPI, frontend package and lockfile root, and Docker
build defaults agree on 1.10.0. The audio daemon retains its independent service
version. CI validates Python/frontend agreement and passes `sonar.projectVersion`
to both scanner modes; it does not use a build number as the release version.

[Runtime reliability PR #542](https://github.com/mpieniak01/Venom/pull/542) is package
C and is reviewed independently. Its lifecycle/restart/replay fixes and tests are
not a second change in D. Preserve those changes when integrating the split
packages. [Rider module PR #24](https://github.com/mpieniak01/venom-module-rider/pull/24)
uses the new core tool contract: qualify the compatible pair before enabling that
optional module. An inactive module does not expand the Light release scope.

## Frozen sources and historical findings

The former combined PRs are diagnostic sources, not the route to this release:

| Source | Frozen commit | Retained tag |
| --- | --- | --- |
| [Core #540](https://github.com/mpieniak01/Venom/pull/540) | `7eec1c9705745b9eedd59e82895553e0330308e4` | `diagnostic/pr540-20261018` |
| [Sonar/release #541](https://github.com/mpieniak01/Venom/pull/541) | `0a1a860fb231544bd72afb3b7bfc9c2496ce9e09` | `diagnostic/pr541-20261018` |

Keep their branches, tags and original evidence for the Snyk investigation and
split-change ledger. Do not merge those combined sources or retarget #541 as a
substitute for the new scoped PRs. Old checks and reviews belong to their original
commits and bases; they do not qualify the rewritten candidates.

The [frozen #541 analysis](https://github.com/mpieniak01/Venom/blob/0a1a860fb231544bd72afb3b7bfc9c2496ce9e09/docs/SONAR_RELEASE_ANALYSIS.md)
retains the 18 October main triage, security issue keys, trust-boundary review and
historical validation. Those findings remain a tracked backlog until their actual
code or reviewed disposition resolves them. D neither marks issues false-positive
nor imports historical test totals as current acceptance. Full's hosted installer
ERROR and known advisory findings are not repaired by the split or version bump;
retain the original Snyk projects and checks. Local lock integrity and a green
Light/CI result cannot replace a failed Full result.

## Sonar configuration boundary

`.sonarcloud.properties` contains only CPD exclusions, encoding and Python version.
Tests and translation dictionaries intentionally repeat shapes and are excluded
from copy/paste metrics only. D adds no issue/security exclusions, rule suppressions
or reduced thresholds. Existing CI source and coverage policy stays in force, as
does the gate wait. The version event may affect the future new-code baseline; it
does not close existing findings. Compare all-code security findings as well as
the new-code gate against the retained report.

Automatic Analysis and CI analysis must not run concurrently. Confirm the actual
cloud Analysis Method before publication; repository files do not switch that
setting. CI supplies projectVersion because Automatic Analysis does not import
coverage or support that version setting in its configuration file.

Sources: [Automatic analysis](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/automatic-analysis),
[Project version parameter](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/analysis-parameters/parameters-not-settable-in-ui).

## Integration and acceptance

Keep D local while A and the atomic B change are reviewed. After both are accepted
on main, rebuild D on that main and inspect its effective diff. Its own changes
must retain A's dependency graph, B's MAF/core initialization and C's accepted
runtime fixes. There is no CI exception for the former 266 branch and no published
stack that requires merging the frozen sources.

Run the release-identity regression in `tests/test_main_internal_helpers.py`,
catalog/group checks, coverage diagnostics, typing and `make pr-fast` on the exact
D candidate. Use the accepted Node24 graph and qualified CI interpreter; record
commands, actual exit codes, changed-lines coverage and skips in the candidate's
validation report. A shared dependency directory may be reused only after the
package and lock dependency metadata match apart from release version fields.
Such reuse is not a new dependency resolution or security qualification.

After authorized publication, require fresh GitHub CI and Sonar results for the
final SHA. Verify 1.10.0 identity, the analysis method and version event, CPD-only
effect of dictionary exclusions, and the unresolved full security backlog. Local
gates do not prove cloud acceptance or authorize operator deployment.

Do not modify an operator Full environment during this split. Any later rollout
uses a validated core/frontend/lock/module pair and preserves the previous pair
for rollback; do not downgrade packages in place. No model loading, service switch,
robot action or merge is performed by this release-preparation package.
