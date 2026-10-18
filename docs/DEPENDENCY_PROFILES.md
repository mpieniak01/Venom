# Dependency profiles: Light/CI release scope

The active config/dependency-profiles.json policy manages only light, ci and build
on Linux x86_64 / Python 3.12. Light uses the selected released Microsoft Agent
Framework components. CI extends the same application requirements with test and
development tools. Build supplies pinned packaging tools; it is not a model runtime.

The five compatibility inputs requirements.txt, requirements-runtime-common.txt,
requirements-docker-minimal.txt, requirements-profile-api.txt and
requirements-profile-web.txt contain the complete Light requirement set. Generated
SCM manifests contain no recursive -r or -c directives.

## Retained legacy scope

Full, Full-CI, ONNX CPU/extras, ONNX GPU, vLLM and Academy are explicitly deferred in
policy metadata. Existing legacy manifests and constraints-hf-onnx.txt retain their
main-branch contents and remain outside generation and active lock qualification.
No new Full-CI input or deferred component lock is published by this release.
The bootstrap and qualification CLI reject a request for a deferred profile before
installation. The metadata does not claim these retained environments are safe,
installable, migrated to MAF, or compatible with the new Light environment.

SCM projects and required security checks remain enabled. A complete Light/CI
audit is evidence for that selected inventory only. It cannot stand in for a Full
SCM scan, and a hosted installation ERROR remains an ERROR. Prior Full/vLLM findings
and the Snyk support investigation are not resolved by changing release scope.

## Inspect generated inputs and locks

Activate the existing repository virtualenv before running Python tooling:

    source .venv/bin/activate
    python scripts/dev/dependency_profiles.py generate --check
    python scripts/dev/dependency_profiles.py audit-locks

Generation writes only active inputs and aliases. The lock audit checks every active
receipt, artifact hash, direct requirement and shared application version. It reports
deferred profile names separately and never labels them qualified.

The six active lock/receipt files are carried from the previously qualified source
without resolving or installing dependencies again. Their profile policy hashes
remain authoritative because the effective Light/CI/build requirement sets did not
change. A receipt's original global policy hash is provenance for the resolution;
unrelated profile removal does not rewrite its artifacts or claim a new resolution.
RESOLVED_ONLY lock integrity is distinct from installation, runtime and security
qualification. Fresh publication checks apply to the new candidate commit.

## Explicit bootstrap

    python scripts/bootstrap_dependency_profile.py --profile ci --venv /explicit/path/to/venv

An existing target requires explicit --update; environments with legacy engines,
system site packages, stale ownership or a mismatched inventory are rejected.
Do not mutate the operator venv to adopt this split. No bootstrap is needed merely
to review it. Storage, hash receipt, package source and binary artifact guards remain
active. The installer does not start services or load models.

## Local security evidence

The audit-security action requires an explicit active profile, exact interpreter,
output directory under docs_dev or test-results, and the SCM organization. It verifies
generated inputs, all active locks, installed inventory and bootstrap tools before
querying component versions and declared minima. Failed preflight invalidates an old
PASS report. Partial, unavailable or inconsistent scan output remains incomplete
ERROR. Local CLI results are not a hosted SCM emulator and cannot override a failed
GitHub security check.
