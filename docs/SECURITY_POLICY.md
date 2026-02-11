# Security Policy

This document defines the official security policy for Venom runtime behavior, configuration exposure, and agent autonomy controls.

## Scope

This policy covers:

- runtime/API security controls for local administration,
- autonomy enforcement for mutating agent actions,
- workspace and execution isolation assumptions,
- minimum testing and quality gates required to prevent regressions.

For dependency/CVE hygiene, see `docs/SECURITY_FIXES.md`.

## Security Model

Venom follows a dual model:

1. Agent safety: the system must prevent autonomous unsafe actions by AI agents.
2. Admin sovereignty: the local operator keeps full control over local configuration.

Operational baseline:

- single-user local administration,
- trusted/private network by default,
- no direct public exposure of backend control endpoints.

## Core Principles

1. Local admin sovereignty
- Local administrator can modify `.env` runtime configuration.
- Policy does not impose hardcoded variable blacklists for localhost admin operations.

2. Localhost-only admin surface
- Administrative config endpoints must be callable only from localhost (`127.0.0.1` / `::1`).
- Remote requests to those endpoints must return `403`.

3. Least privilege for agent execution
- Mutating operations require explicit autonomy level checks.
- Unknown/uncategorized mutating paths are treated as denied by default.

4. Defense in depth
- Host-level request restrictions + autonomy permissions + deployment isolation.

## API and Configuration Security Requirements

The following endpoints are treated as administrative and must enforce localhost-only access:

- `POST /api/v1/config/runtime`
- `GET /api/v1/config/backups`
- `POST /api/v1/config/restore`

Additional requirement:

- `GET /api/v1/config/runtime` must return secrets in masked form (`mask_secrets=True`).

## Autonomy Enforcement Requirements

All mutating skill paths must be guarded by permission checks. Standard enforcement helpers:

- `require_file_write_permission()`
- `require_shell_permission()`
- `require_core_patch_permission()`

Minimum protected operations:

- file write/edit skills,
- shell execution skills,
- core patch/rollback operations,
- MCP import paths that execute shell commands.

## Isolation Boundaries

1. Core code (`venom_core/`)
- Treated as protected system area.
- Agent-driven mutation must be explicitly gated and auditable.

2. Workspace (`workspace/`)
- Primary mutable sandbox for agent-generated artifacts.

3. MCP/runtime extensions
- Executed as controlled external processes and still subject to autonomy and host policies.

## Testing and Quality Gates

Security changes are valid only when regression checks pass.

Required checks before merge:

- `pre-commit run --all-files`
- `mypy venom_core`
- `make check-new-code-coverage`
- `make pr-fast`

Recommended release validation:

- `make pytest`
- `make sonar-reports`

Security-focused coverage must include:

- localhost-only endpoint access behavior (`403` for remote host),
- secret masking on runtime config reads,
- autonomy violation on blocked mutating actions.

See also: `docs/TESTING_POLICY.md` and `docs/AUTONOMY_GATE.md`.

## Deployment Constraints

This policy assumes non-public backend control surfaces.

If remote/public exposure is required:

- place a reverse proxy in front,
- enforce authentication/authorization,
- restrict access to trusted operators only.

See: `docs/DEPLOYMENT_NEXT.md`.
