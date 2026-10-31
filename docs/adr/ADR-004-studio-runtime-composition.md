# ADR-004: Separate Venom and Studio application compositions

Date: 2026-10-31. Status: Accepted for implementation; release qualification is
recorded separately. Partially supersedes the single-deployment decision in
[ADR-003](ADR-003-chat-2-shell.md), preserving its conversation/safety contracts.

## Context

The isolated `/chat2` route removes the old cockpit and its telemetry from the
conversation tree. It still runs inside an application with all Full routes and
a backend that initializes unrelated services. A theme cannot change that
startup boundary. The operator needs a focused conversation entry while keeping
the existing application and environment data.

## Decision

1. Keep Next.js/FastAPI. Launch `venom` or `studio` as explicit application
   variants, independently of Full/Light and dev/preprod. Stop the owning variant
   before switching: do not run two owners over shared data or local engines.
2. Studio uses `web-studio`, with only `/` and `/chat2` and its own route discovery,
   build/cache/public output and metadata. Reuse shared Chat 2.0 components,
   controller, providers, fonts/global styles and installed `web-next` dependencies.
   Do not copy screens, business logic, optional-module mirrors or proxy code.
   Hide the classic `/chat` link only in standalone Studio; keep the default
   behavior of the shared component in the existing app.
3. Start `venom_core.studio_main:app`. Mount an explicit subset of existing route
   functions with the same schemas, guards, admission, budgets, request identity,
   history and cancellation semantics. Do not import Full's entry point,
   duplicate handlers or silently fall back to missing Full endpoints. Shared
   theme persistence retains GET/POST config/runtime with the Full localhost guard,
   without copying the configuration screen.
4. Reuse the selected environment's configuration and persisted SessionStore,
   memory/material roots, provider state and queue/cache namespaces. There is no
   Studio database, migration or second queue. Dev/preprod isolation and preprod
   read-only policy remain. Browser storage is origin-local with shared keys;
   it does not replace server history.
5. Defer the existing Orchestrator and its execution/memory dependencies until
   supported Normal/MAF use. Preserve real Direct memory ingestion: construct the
   existing VectorStore when needed. Construct configured STT/TTS on first use,
   without boot warmup. Do not add automatic RAG, training, screens or another
   model loader. Preserve existing runtime selection and engine ownership rules.
6. Variant start/stop/status use the common resolver, serialized lifecycle and
   proxy. Artifact identity covers each app and shared inputs, including the
   worklet. Explicit variant stop retires only verified API/UI and owned local
   engines; foreign, replaced or unverifiable records fail safely. Drain active
   and native work before cleanup. The narrower legacy API/UI stop stays distinct.
7. Automate route/schema/security parity, handler identity, prohibited imports,
   fake conversation/audio flows, required assets and cleanup. Build, operational
   measurements and real-provider/audio qualification are separate evidence.
   Fake tests or route counts do not prove RAM savings or production acceptance.
   Real provider Test Zero remains operator-request-only.

## Consequences

The frontend/API can have smaller startup surfaces while retaining one
conversation implementation and the same data contract. Separate artifacts add
lifecycle work without introducing another framework or storage system. Global
styles and the dependency installation remain shared. Normal/MAF, ingestion and
voice can load heavier existing components after startup. Measure those states
separately; do not promise a permanently lightweight process.

## Rollback

Stop the owning Studio variant and start Venom in the same environment through
its verified launcher. No data deletion or history migration is required.
The optional `/chat2` route in Full keeps its build-time feature-flag contract;
it is distinct from selecting the standalone application variant.

[Operator guide](../STUDIO.md) · [Polish ADR](../PL/adr/ADR-004-studio-runtime-composition.md)
