# Docker Package Release Guide (Minimal MVP)

This document defines the official way to publish Docker images for Venom Minimal MVP.

## Quick Answer

- Yes: in manual mode you use a real button in GitHub UI: `Actions` -> `Docker Publish (Minimal)` -> `Run workflow`.
- For tag mode: first make sure commit is on `main`, then create and push tag `vX.Y.Z`. Pushing the tag starts publish automatically.

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
2. If needed, push latest commit on `main`:
```bash
git push origin main
```
3. Create and push release tag:
```bash
git tag v1.0.0
git push origin v1.0.0
```
4. GitHub Actions runs `Docker Publish (Minimal)` automatically.

Tags pushed to GHCR:
- `sha-<short_sha>`
- `v1.0.0`
- `latest`

### Mode B: Manual publish (for test/RC builds)

Use this mode to publish an ad hoc package without creating a release tag.

1. Open repository in GitHub.
2. Go to `Actions` tab.
3. Select workflow: `Docker Publish (Minimal)`.
4. Click `Run workflow` (top-right).
5. Choose branch: `main`.
6. Set required input: `confirm_publish=true`.
7. Optional: set `custom_tag`, `push_latest`.
8. Click green `Run workflow` button to start.

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
