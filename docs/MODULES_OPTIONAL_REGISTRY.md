# Optional Modules Registry (Pre-161)

This document describes how to enable optional API modules without hard-coding new router imports in `venom_core/main.py`.

## 1. Built-in optional module

Built-in manifest currently includes:
- `module_example` -> `venom_core.api.routes.module_example:router`

Enable with:
- `FEATURE_MODULE_EXAMPLE=true`

## 2. Extra optional modules (config)

Use `API_OPTIONAL_MODULES` in this format:

`module_id|module.path:router|FEATURE_FLAG|MODULE_API_VERSION|MIN_CORE_VERSION`

Examples:

`API_OPTIONAL_MODULES=my_mod|acme_mod.api:router|FEATURE_ACME|1|1.5.0`

`API_OPTIONAL_MODULES=mod_a|pkg.a:router|FEATURE_A|1|1.5.0,mod_b|pkg.b:router`

Fields:
- `module_id` (required)
- `module.path:router` (required)
- `FEATURE_FLAG` (optional)
- `MODULE_API_VERSION` (optional)
- `MIN_CORE_VERSION` (optional)

## 3. Compatibility contract

Core checks:
- `CORE_MODULE_API_VERSION` (default: `1`)
- `CORE_RUNTIME_VERSION` (default: `1.5.0`)

If module compatibility does not match:
- module router is skipped,
- startup continues,
- warning is logged.

## 4. Safety behavior

Invalid entries in `API_OPTIONAL_MODULES`:
- do not crash startup,
- are ignored,
- produce warnings.

## 5. Phase 160 objective

The registry is preparatory infrastructure:
- it improves module separation,
- it does not force private/business logic into OSS core,
- it keeps default core behavior stable when modules are disabled.
