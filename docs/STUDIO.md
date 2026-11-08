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
separate browser storage. A thread with server-side history survives a build
change or restart. The Studio conversation list is also scoped to the browser
origin. Browser storage is not a backup of server history.

Studio shares Chat 2.0 components, fonts and global styles, but has its own route
tree, Next build output, dev cache and public assets. It reuses the installed
`web-next/node_modules` tree, without a second dependency installation. Preparation
writes Studio metadata and copies the required audio-capture worklet from the
shared source, refreshing it on change. Both apps use the same streaming proxy
and artifact lifecycle.

When an explicit build is needed, run from the repository while that UI is stopped:

```bash
make web-build VENOM_VARIANT=studio PROFILE=full ENVIRONMENT=dev
LLM_MODEL_NAME=gemma4:e4b make start-studio PROFILE=full ENVIRONMENT=dev START_WEB_MODE=standalone
```

This option is available for Studio in dev. The regular `make start-studio`
uses Turbopack for development. Both commands use the same dev data.

A prepared artifact must match its sources/shared inputs, public configuration,
Node version and environment. Starting it does not implicitly rebuild it. Do not
rebuild the active UI's artifact. See [UI lifecycle](PL/WEB_LIFECYCLE.md).

## Studio for everyday use

Studio preloads the selected local Ollama model before reporting API readiness
when `LLM_WARMUP_ON_STARTUP` is enabled. The attempt takes up to 30 seconds.
If the model is unavailable, startup logs the result and the user can select
a runtime in chat. Startup does not warm remote providers.

The Studio launcher defaults to a 4096-token context, one concurrent
generation and one resident Ollama model. Explicit settings take precedence.
Venom also defaults to one concurrent generation and retains its context
profile for longer tasks. Dev and preprod retain their own data and write policy.

| Mode | Resource usage |
|---|---|
| Direct | Shared response stream and SessionStore history. Images and files on attachment. Indexing through explicit note ingest. |
| Normal | Lightweight local Ollama text chat with history. Explicit note lookup uses LanceDB, with a scoped name lookup when a source is unambiguous. Semantic search loads embeddings on demand. |
| Voice | The first transcription or synthesis loads the AudioEngine. Later turns reuse it. |
| MAF and tools | The first request for this path initializes the Orchestrator and agents. |
| Venom Full | Full screens and API for multistep tasks, development and diagnostics. Notes and history are shared in the same environment. |

```bash
make start-studio PROFILE=full ENVIRONMENT=dev
```

For comparison, `NEXT_PUBLIC_STUDIO_DIRECT_AUTO_INDEX=1` restores automatic
indexing and `NEXT_PUBLIC_STUDIO_LIGHT_NORMAL=0` selects the previous Normal
path. Set these variables at build time for prebuilt UI.

### Embeddings in a separate process

For occasional semantic searches on Linux or WSL, `STUDIO_EMBEDDING_PROCESS=1`
uses an on-demand subprocess. It exits after `STUDIO_EMBEDDING_IDLE_SECONDS`.
Zero selects 120 seconds in this mode. The next semantic search pays the
model startup cost. The option defaults to off for smooth successive lookups.

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
