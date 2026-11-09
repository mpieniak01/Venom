# OpenAPI contract maintenance

The committed `openapi/openapi.json` describes the **Full core HTTP API**.
Studio shares its route handlers and TypeScript types. The contract does not
include optional modules selected by an operator's local configuration.

## Update and check

Use the repository Python dependency profile and the frontend lockfile:

```bash
source .venv/bin/activate
npm --prefix web-next ci
make openapi-codegen-types
make openapi-check
```

Commit both `openapi/openapi.json` and
`web-next/lib/generated/api-types.d.ts`. The generator version and its transitive
dependencies are pinned in `web-next/package-lock.json`. `make openapi-export`
updates only the JSON; use `openapi-codegen-types` to update the complete pair.

`make openapi-check` generates into `test-results/openapi/`, then checks:

- semantic equality of the committed JSON and the current core schema;
- byte equality of the generated TypeScript declarations;
- equality of every Studio HTTP operation and component with the Full schema.

The check does not rewrite committed files. Missing files, stale contracts,
failed imports/codegen and Studio incompatibilities fail the command. Local
`make pr-fast` (including the pre-push hook) runs it for backend, exporter,
contract, generator dependency and CI configuration changes. CI uses the same
command, rather than only uploading freshly generated artifacts.

Exports run in a fresh interpreter, with an explicit environment and a temporary
working directory. They do not read the operator's dotenv file, inherit feature
flags or optional modules, start ASGI lifespans, invoke endpoints, or run model
qualification. Application runtime configuration is unchanged. WebSocket
protocols remain covered by their own route tests; OpenAPI describes HTTP.

## Optional module contracts

Export one explicitly selected, trusted module into a separate artifact:

```bash
python scripts/export_openapi.py --profile module \
  --module-manifest /absolute/path/to/module/module.json \
  --output test-results/openapi/modules/example.json
```

The module manifest and router must load successfully. Its feature flag is
enabled only in the isolated export process; unrelated modules and core routes
are excluded. This imports module code, so use reviewed module revisions.
Maintain a module's snapshot and generated client in that module's repository,
with its own dependencies and revision pinned. The core gate must work when
no optional modules are installed. A module export cannot overwrite the shared
core JSON.

For a standalone Studio artifact:

```bash
python scripts/export_openapi.py --profile studio \
  --output test-results/openapi/studio.json
```

## Repair baseline

The first complete core refresh replaces version metadata `1.5.0` with the
application's `1.10.0`, adds 27 previously undocumented core paths, and updates
the optional `runtime` query parameter on model runtime capabilities.
Nine Google Home paths move out of the core snapshot because they belong to an
optional module. This changes documentation and generated declarations only;
no live route is removed. The baseline contains 246 core paths.

[Polska instrukcja](PL/OPENAPI_CONTRACTS.md)
