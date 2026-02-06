# Docker Package Release Guide (Minimal MVP)

This document defines the official way to publish Docker images for Venom Minimal MVP.

## Scope

- Backend image: `ghcr.io/<owner>/venom-backend`
- Frontend image: `ghcr.io/<owner>/venom-frontend`
- Workflow: `.github/workflows/docker-publish.yml`

## Safety Rules (Mandatory)

1. Do not publish images from feature branches.
2. Stable release uses semantic version tag: `vMAJOR.MINOR.PATCH` (example: `v1.2.3`).
3. Manual publish is allowed only from `main`.
4. Manual publish requires explicit confirmation: `confirm_publish=true`.

These rules are enforced by workflow preflight checks.

## Release Modes

### Mode A: Tagged release (recommended for official package)

Use this mode for a stable package release.

1. Ensure `main` is green and up to date:
```bash
git checkout main
git pull --ff-only
```
2. Create and push release tag:
```bash
git tag v1.0.0
git push origin v1.0.0
```
3. GitHub Actions runs `Docker Publish (Minimal)` automatically.

Tags pushed to GHCR:
- `sha-<short_sha>`
- `v1.0.0`
- `latest`

### Mode B: Manual publish (for test/RC builds)

Use this mode to publish an ad hoc package without creating a release tag.

1. Open: GitHub `Actions` -> `Docker Publish (Minimal)` -> `Run workflow`.
2. Branch must be `main`.
3. Required input:
   - `confirm_publish=true`
4. Optional inputs:
   - `custom_tag` (example: `rc1`, `mvp-test`)
   - `push_latest=true` only if you intentionally want to move `latest`.

Typical tags in manual mode:
- always: `sha-<short_sha>`
- optional: `<custom_tag>`
- optional: `latest` (only when `push_latest=true`)

## Verification Checklist After Publish

1. Workflow status is green (`preflight` + both image matrix jobs).
2. GHCR contains both images:
   - `venom-backend`
   - `venom-frontend`
3. Expected tags are visible.
4. Pull smoke test from clean host:
```bash
docker pull ghcr.io/<owner>/venom-backend:<tag>
docker pull ghcr.io/<owner>/venom-frontend:<tag>
```

## Rollback / Recovery

If wrong package was published:

1. Do not force-delete tags in panic.
2. Publish a corrected tag immediately (example: `v1.0.1`).
3. If needed, update deployment to pinned tag (avoid `latest`).

## Notes

- `docker-sanity` validates build and smoke on PR; it does not publish images.
- For trusted LAN testing policy and runtime notes, see `docs/DEPLOYMENT_NEXT.md`.
