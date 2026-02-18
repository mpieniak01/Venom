# Optional Modules: Authoring and Operations Guide (EN)

This guide describes a universal, public way to develop and operate optional modules in Venom without hard-coding new imports in `venom_core/main.py`.

## 1. Design goals

- Keep OSS core stable when modules are disabled.
- Allow independent module development and release cadence.
- Enforce compatibility (`module_api_version`, `min_core_version`) at startup.
- Gate backend and frontend separately with feature flags.

## 2. Registry model

Two module sources are supported:
- built-in optional manifest (in core),
- external manifest from `API_OPTIONAL_MODULES`.

Manifest format:

`module_id|module.path:router|FEATURE_FLAG|MODULE_API_VERSION|MIN_CORE_VERSION`

Fields:
- `module_id` (required): unique module key.
- `module.path:router` (required): import path to FastAPI router.
- `FEATURE_FLAG` (optional): backend flag, for example `FEATURE_ACME`.
- `MODULE_API_VERSION` (optional): contract version.
- `MIN_CORE_VERSION` (optional): minimal compatible core version.

Examples:
- `API_OPTIONAL_MODULES=my_mod|acme_mod.api:router|FEATURE_ACME|1|1.5.0`
- `API_OPTIONAL_MODULES=mod_a|pkg.a:router|FEATURE_A|1|1.5.0,mod_b|pkg.b:router`

## 3. Compatibility contract

Core compares module manifest against:
- `CORE_MODULE_API_VERSION` (default `1`)
- `CORE_RUNTIME_VERSION` (default `1.5.0`)

If incompatible:
- module is skipped,
- startup continues,
- warning is logged.

Invalid manifest entries:
- do not crash startup,
- are ignored,
- produce warnings.

## 4. Module lifecycle (recommended)

1. Develop module in separate repository/package.
2. Publish installable artifact (wheel/source package).
3. Install artifact in runtime environment.
4. Register module via `API_OPTIONAL_MODULES`.
5. Enable backend feature flag.
6. Enable frontend flag (if module exposes UI).
7. Validate health and logs.
8. Roll back by disabling flag or removing manifest entry.

## 5. Module example: management and toggles

Current built-in optional module:
- `module_example` -> `venom_core.api.routes.module_example:router`

Backend enable:
- `FEATURE_MODULE_EXAMPLE=true`

Frontend navigation enable:
- `NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE=true`

Module API base path:
- `/api/v1/module-example/*`

Disable module safely:
- set `FEATURE_MODULE_EXAMPLE=false` (backend off),
- set `NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE=false` (hide UI entry),
- optionally remove matching item from `API_OPTIONAL_MODULES`.

## 6. Operational runbook (quick checks)

1. Confirm flags:
- backend: `FEATURE_*`
- frontend: `NEXT_PUBLIC_FEATURE_*`
2. Confirm manifest parsing:
- `API_OPTIONAL_MODULES` has correct `|` and `,` delimiters.
3. Confirm import path:
- `module.path:router` is importable in runtime.
4. Confirm compatibility:
- `MODULE_API_VERSION` and `MIN_CORE_VERSION` match core.
5. Confirm logs:
- module loaded/skipped with explicit reason.

## 7. Testing and quality gates

Minimum verification for module platform behavior:
- `tests/test_module_registry.py`
- `web-next/tests/sidebar-navigation-optional-modules.test.ts`

Repository hard gates for code changes:
- `make pr-fast`
- `make check-new-code-coverage`

## 8. Scope boundary

This mechanism provides modular infrastructure only.
It does not force private/business logic into OSS core.
