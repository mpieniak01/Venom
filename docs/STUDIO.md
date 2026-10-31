# Venom and Studio: application runtimes

Venom and Studio are two application variants in the same repository. Venom
keeps the existing screens and Full API. Studio serves Chat 2.0 from its own
Next.js application and a smaller FastAPI entry point. Both reuse the same
conversation code, provider adapters and environment-owned data.

This guide covers the Studio API, standalone web application, launch/switch
lifecycle and verified shutdown. See [ADR-004](adr/ADR-004-studio-runtime-composition.md)
and the [conversation features and limits](CHAT_2.md).

## Choose and switch

Run from the configured repository with its existing dependencies. These examples
assume a stopped development instance using repository defaults. An installed
instance launcher can have different tools, ports and ownership records: use
its configured procedure rather than replacing those settings.

```bash
make start-venom PROFILE=full ENVIRONMENT=dev
make status-venom ENVIRONMENT=dev
make stop-venom ENVIRONMENT=dev

make start-studio PROFILE=full ENVIRONMENT=dev
make status-studio ENVIRONMENT=dev
make stop-studio ENVIRONMENT=dev
```

Stop the current owner before starting the other variant. Both variants own the
same selected environment's data and shared local runtime resources. A running
peer or unverified listener blocks the switch. Return by stopping Studio and
starting Venom in the same environment; no data migration or deletion is needed.

| Selection | Venom | Studio |
| --- | --- | --- |
| UI workspace | `web-next` | `web-studio` |
| ASGI entry | `venom_core.main:app` | `venom_core.studio_main:app` |
| Web routes | Existing application | `/` redirects to `/chat2`; Chat 2.0 only |
| Chat 2.0 flag | Explicit variant sets `false` | Variant enables its conversation entry |
| Server data | Selected environment | Same environment, without a second data root |

Open the UI address reported by the launcher. Repository defaults are UI/API
3000/8000 in dev and 3100/8100 in preprod. Studio has no classic `/chat` page or
link. The optional `/chat2` route inside the existing Venom application remains
a separate compatibility path described in [Chat 2.0](CHAT_2.md).

Application variant, Full/Light and environment are independent selections:

```bash
make start-studio PROFILE=light ENVIRONMENT=dev
make start-studio PROFILE=full ENVIRONMENT=preprod
make stack-plan VENOM_VARIANT=studio PROFILE=full ENVIRONMENT=preprod
```

Stop the active owner before changing environment or profile. Dev/preprod retain
separate configuration, databases, logs, storage, cache/queue namespaces and
provider state. Preprod stays read-only; Studio does not relax that policy.
Prod remains unused. Do not copy private environment files or secrets to switch.

## Shared contracts, separate artifacts

Studio mounts a subset of the existing route functions, schemas and dependencies.
Direct, supported Normal/MAF, runtime/model selection, OpenRouter quotes,
materials, session history, scoped Stop and STT/TTS retain the same admission,
origin, budget and cancellation rules. Other Full endpoints are absent; Studio
does not silently route them to another API.
Shared theme persistence still uses `GET`/`POST /api/v1/config/runtime` with
the existing Full localhost guard; a separate configuration screen is not copied.

`MEMORY_ROOT`, state files, SessionStore, material IDs and saved provider state
remain owned by the environment. Switching does not migrate, clone or erase them.
The frontend uses the shared providers/controller and browser storage keys.
Browser drafts and active sessions are origin-local: another UI origin has
separate browser storage, and a new build can initialize a new current thread.
Use the conversation list to reopen a saved session; browser storage is not a
server-history backup.

Studio shares Chat 2.0 components, fonts and global styles, but has its own route
tree, Next build output, dev cache and public assets. It reuses the installed
`web-next/node_modules` tree, without a second dependency installation. Preparation
writes Studio metadata and copies the required audio-capture worklet from the
shared source, refreshing it on change. Both apps use the same streaming proxy
and artifact lifecycle.

When an explicit build is needed, run from the repository while that UI is stopped:

```bash
make web-build VENOM_VARIANT=studio PROFILE=full ENVIRONMENT=preprod
```

A prepared artifact must match its sources/shared inputs, public configuration,
Node version and environment. Starting it does not implicitly rebuild it. Do not
rebuild the active UI's artifact. See [UI lifecycle](PL/WEB_LIFECYCLE.md).

## Lazy services and memory

Studio skips unrelated Full startup services and optional-module registration.
It adds no RAG, training, other screens, new queue or storage system. Existing
memory behavior remains available through shared handlers.

- Direct starts without constructing orchestration. Its existing successful-turn
  memory/ingest call can initialize the existing VectorStore on demand.
- The first supported Normal/MAF request creates the existing Orchestrator and
  required dispatcher, memory and execution dependencies. There is no alternate MAF.
- STT/TTS creates the configured AudioEngine on first use, without speech warmup
  at boot. Opening the page does not request the microphone.
- Local LLM processes/models follow existing configuration and admission rules.
  The API composition does not introduce another automatic model loader or
  authorize paid provider calls.

Measure startup separately from the state after ingest, Normal/MAF or voice.
These operations can load heavier components. Smaller route counts do not prove
RAM savings, lower latency or production readiness. Shared global CSS and the
shared dependency installation remain explicit implementation boundaries.

## Verified stop

Use the owning variant's stop command and environment. `stop-venom`/`stop-studio`
retire verified UI/API owners and configured/recorded owned local engines.
Identity and ownership records are checked before signalling. Foreign, replaced
or unverifiable records cause an error instead of adoption by process name or
port. Resolve an ownership conflict before switching variants.

Legacy `make stop` remains the narrower environment API/UI stop. It is not the
explicit variant teardown contract. Do not substitute global process-name kills.
Local stop does not destroy provider accounts or rented cloud instances; a
cancelled paid request can retain pending costs under its provider contract.

Studio API shutdown drains existing queued/active work and native cleanup before releasing
owned resources. PID status alone does not prove model memory was released.
Receipt guards assume serialized launcher writers; they are not a general atomic
filesystem compare-and-swap protocol.

## Qualification boundary

Fake tests verify code/lifecycle contracts, not a real microphone, model quality,
paid execution or production deployment. This guide does not assert that a build,
release gate or real-provider qualification was run. Use recorded acceptance for
the tested revision. Each real provider Test Zero requires a separate instruction
under the [provider policy](PROVIDER_TEST_ZERO_POLICY.md).

[Polska instrukcja](PL/STUDIO.md)

Local qualification and measured limits: [Studio acceptance](STUDIO_ACCEPTANCE.md).
