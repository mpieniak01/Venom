# Full/Light launch profiles

The default is **Full/dev with Turbopack**, one API worker and the saved provider/model.

```bash
make start
make start PROFILE=light ENVIRONMENT=dev
make start PROFILE=full ENVIRONMENT=preprod
make start PROFILE=light ENVIRONMENT=preprod
make stack-plan ENVIRONMENT=preprod
make status ENVIRONMENT=preprod
make stop ENVIRONMENT=preprod
```

Dev and preprod retain separate databases, logs, data, cache/queue namespaces,
PID records, Next artifacts and mutable provider state. Full and Light within
one environment share its data. Preprod is read-only. Prod remains unused.

Full preserves configured interactive features and background policies. Light
preserves provider/model and voice quality, pauses background work and disables
LLM warmup. It does not guarantee lower RAM with identical audio/model readiness.

A shared resolver handles stack and API/UI components. Launches serialize host
runtime admission; PID control verifies identity and affects only owned processes.
The API proxy must target its own environment. Unverified old processes require
an explicit guarded migration, not automatic adoption.

Repository defaults are dev 8000/3000 and preprod 8100/3100. An installed host
launcher retains instance-specific tools/ports; use it rather than replacing
its configuration with repository defaults.

Legacy dev/turbo/lowmem/preprod aliases delegate to this contract and are being
retired after the next release/migration. Bundler diagnostics, provider/model,
GPU, CI/build tooling and isolated engine dependencies are technical settings,
not more application profiles.

See the detailed [Polish contract and migration map](PL/STACK_PROFILES.md),
[UI artifact lifecycle](PL/WEB_LIFECYCLE.md), [environment matrix](ENVIRONMENTS_SUPPORT.md)
and [dependency boundaries](DEPENDENCY_PROFILES.md).
Docker images currently install Light dependencies; a Full label does not
qualify missing voice/RAG/module dependencies or production deployment.
