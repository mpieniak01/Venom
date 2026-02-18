# Optional Modules: Authoring and Operations Guide (EN)

This guide describes the universal public model for developing and operating optional modules in Venom, without hard-coded imports in `venom_core/main.py`.

## 1. Project goals

- Keep OSS core stable when modules are disabled.
- Enable independent module development and release cadence.
- Enforce compatibility (`module_api_version`, `min_core_version`) at startup.
- Separate backend and frontend feature flags.

## 2. Registry model

There is one supported source for product modules:
- external manifest entries from `API_OPTIONAL_MODULES`.
- core does not maintain a built-in hardcoded module list.

Preferred format (no config duplication from manifest):

`API_OPTIONAL_MODULES=manifest:/home/ubuntu/venom/modules/<module-repo>/module.json`

Legacy format (backward compatibility):

`module_id|module.path:router|FEATURE_FLAG|MODULE_API_VERSION|MIN_CORE_VERSION`

Fields for legacy format:
- `module_id` (required): unique module key.
- `module.path:router` (required): import path to FastAPI router.
- `FEATURE_FLAG` (optional): backend flag, for example `FEATURE_ACME`.
- `MODULE_API_VERSION` (optional): module contract version.
- `MIN_CORE_VERSION` (optional): minimal compatible core version.

Examples:
- `API_OPTIONAL_MODULES=manifest:/home/ubuntu/venom/modules/venom-module-example/module.json`
- `API_OPTIONAL_MODULES=manifest:/home/ubuntu/venom/modules/mod-a/module.json,manifest:/home/ubuntu/venom/modules/mod-b/module.json`
- legacy: `API_OPTIONAL_MODULES=my_mod|acme_mod.api:router|FEATURE_ACME|1|1.5.0`

## 3. Compatibility contract

Core compares module manifest values with:
- `CORE_MODULE_API_VERSION` (default `1`)
- `CORE_RUNTIME_VERSION` (default `1.5.0`)

If incompatible:
- module is skipped,
- startup continues,
- a warning is logged.

Invalid manifest entries:
- do not crash startup,
- are ignored,
- produce warnings.

## 4. Module structure (target model only)

### 4.1. Module in a separate repository (target for products)

Required local workspace convention:
- modules collection directory: `/home/ubuntu/venom/modules`
- each module is its own repository inside that collection

Example:
- `/home/ubuntu/venom/modules/venom-module-example`

```text
/home/ubuntu/venom/
├─ venom_core/                         # core repository
├─ web-next/                           # core frontend
│  ├─ app/
│  │  └─ [moduleSlug]/page.tsx         # dynamic host route
│  ├─ lib/generated/
│  │  └─ optional-modules.generated.ts # auto-generated from module.json
│  ├─ scripts/
│  │  └─ generate-optional-modules.mjs # frontend manifest generator
│  └─ components/layout/
│     └─ sidebar-helpers.ts            # menu from module manifests
└─ modules/                            # module repository collection
   └─ venom-module-example/            # separate module repo (preferably private)
      ├─ pyproject.toml
      ├─ README.md
      ├─ module.json                   # module metadata (id, versions, entrypoints)
      ├─ venom_module_<slug>/
      │  ├─ __init__.py
      │  ├─ manifest.py               # module metadata helpers
      │  ├─ api/
      │  │  ├─ __init__.py
      │  │  ├─ routes.py              # FastAPI router exported to core
      │  │  └─ schemas.py             # Pydantic API schemas
      │  ├─ services/
      │  │  └─ service.py             # module domain logic
      │  └─ connectors/
      │     └─ github.py              # optional integrations (env secrets only)
      ├─ web_next/                     # module frontend (separate from core web-next)
      │  ├─ page.tsx                  # main module screen (e.g. /module-example)
      │  ├─ components/
      │  │  └─ ModuleExamplePanel.tsx
      │  ├─ i18n/
      │  │  ├─ pl.ts
      │  │  ├─ en.ts
      │  │  └─ de.ts
      │  └─ api/
      │     └─ client.ts
      └─ tests/
         ├─ test_routes.py
         └─ test_service.py
```

In Venom core, module integration should stay limited to:
- module package installation,
- module registration through `API_OPTIONAL_MODULES`,
- enabling feature flags,
- frontend generator run (`node web-next/scripts/generate-optional-modules.mjs`).

How to add a new module screen:
1. Create screen in module repo, e.g. `web_next_<module_id>/page.tsx`.
2. In `module.json` set frontend metadata:
   - `nav_path` (e.g. `/module-example`)
   - `feature_flag` (e.g. `NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE`)
   - `component_import` (relative import from `web-next/lib/generated/optional-modules.generated.ts`, e.g. `../../../modules/venom-module-example/web-next/page`)
3. Run generator to refresh `optional-modules.generated.ts`.
4. `web-next/app/[moduleSlug]/page.tsx` and navigation consume generated manifest (no manual core route/menu edits).
5. When flag is disabled, screen disappears from navigation and is unavailable by URL.

Module i18n (important):
- keep module translations in module repo (e.g. `web_next/i18n/pl.ts`, `en.ts`, `de.ts`),
- do not add module-specific keys to core global locales (`web-next/lib/i18n/locales/*`),
- use `frontend.nav_labels` in module manifest for localized navigation labels.

Single workstation operations:
- `make modules-status` (core + modules status),
- `make modules-branches` (active branches in core + modules),
- `make modules-pull` (`pull --ff-only` for core + modules),
- `make modules-exec CMD='git status -s'` (same command across workspace).

### 4.2. Minimal required module files

1. `api/routes.py` exposing `router`.
2. `api/schemas.py` with request/response models.
3. `services/service.py` with domain logic.
4. `pyproject.toml` (installable package metadata).
5. `README.md` with env/flag setup.
6. Module tests (`tests/*`).

## 5. Module lifecycle (recommended)

1. Develop module in separate repository/package.
2. Publish installable artifact (wheel/source package).
3. Install artifact in runtime environment.
4. Register module via `API_OPTIONAL_MODULES` using `manifest:/.../module.json`.
5. Enable backend feature flag.
6. Enable frontend feature flag (if UI exists).
7. Validate health and logs.
8. Roll back by disabling flag or removing module manifest entry.

## 6. Module Example: management and toggles

`module_example` is a reference module and should follow full separate-repo model (`/home/ubuntu/venom/modules/venom-module-example`).
Operationally, external module model (4.1) is the standard.

Enable backend:
- `FEATURE_MODULE_EXAMPLE=true`

Enable frontend navigation:
- `NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE=true`

Module API base path:
- `/api/v1/module-example/*`

Safe disable:
- set `FEATURE_MODULE_EXAMPLE=false` (backend off),
- set `NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE=false` (hide UI entry),
- optionally remove related entry from `API_OPTIONAL_MODULES`.

## 7. Operational runbook (quick checklist)

1. Check flags:
- backend: `FEATURE_*`
- frontend: `NEXT_PUBLIC_FEATURE_*`
2. Check manifest:
- `API_OPTIONAL_MODULES` points to existing `module.json`.
- prefer `manifest:/.../module.json` over legacy `module_id|...`.
3. Check import path:
- `module.path:router` is importable in runtime.
4. Check compatibility:
- `MODULE_API_VERSION` and `MIN_CORE_VERSION` match core.
5. Check logs:
- module is loaded/skipped with explicit reason.

## 8. Testing and quality gates

Minimum module platform verification:
- `tests/test_module_registry.py`
- `web-next/tests/sidebar-navigation-optional-modules.test.ts`

Required hard gates for code changes:
- `make pr-fast`
- `make check-new-code-coverage`

## 9. Scope boundary

This mechanism provides modular infrastructure only.
It does not move private/business logic into OSS core.
