# Studio: local acceptance

2026-10-31. Application code: `c446c262`; delivery branch: `codex/group-b-venom-chat-2`.
S01–S04 accepted locally. Internal review closed the confirmed P1/P2 findings.
GitHub publication, external CI and Sonar qualification have not been performed.
See [runtime guide](STUDIO.md) and [ADR-004](adr/ADR-004-studio-runtime-composition.md).

## Delivered behavior

Studio has its own Next app, build and cache, with `/chat2`, a root redirect and
error routes. It uses the existing shared conversation components and 22 API
paths / 27 operations implemented by the same Full handlers and schemas.
Session history, materials, provider selection and environment storage remain
shared; no new database, queue namespace or model directory is introduced.

`start/stop-venom` and `start/stop-studio` are explicit Make targets. A conflicting
or unverified owner blocks switching. Stop and failed-start rollback bind to
original process identities, preserve replaced ownership files and retire only
owned resources. Existing resources reused by a failed start remain intact.

## Evidence

- `make pr-fast`: PASS, 1468 backend cases, 342 component cases and frontend unit suites; 10 standalone Studio cases. Changed-line coverage 93.68% (repository threshold 80%); all 14 file floors passed. This branch comparison also includes earlier Chat 2.0 changes.
- `make test-ci-lite`: 898 PASS. Critical API/lifecycle/shell regressions: 146 PASS. UI lifecycle: 18 PASS, including real harmless process retirement and receipt replacement.
- `mypy venom_core`: 479 source files PASS; startup controller/rollback typing PASS. PL/EN/DE locale parity, architecture, catalog/groups and normal commit hooks PASS.
- Standalone production Turbopack build: PASS; manifest contains only root, Chat 2.0 and error routes. Existing browser acceptance: 58 assertions PASS on fake API/audio, no real provider or microphone calls, no uncaught/hydration errors.
- All 18 distinct operations exercised by the browser are covered by actual Studio OpenAPI. Required capture worklet is served with the same bytes as its shared source. Five classic UI routes return 404; no classic link/sidebar mounts.
- Real Full/dev/Turbo start and passive classic-chat DOM PASS. Real Studio/dev/Turbo start and passive DOM/API/model selection PASS. Stop Venom and stop Studio each left no owned UI/API/Ollama listeners or loaded Ollama models. Studio was restarted and left available locally.
- Existing saved history was read through Studio from the shared SessionStore. Private environment-file hashes and selected model remained unchanged.

Actual startup exposed a nested npm alias dropping UI arguments; direct launcher
commands plus real npm regression fixtures cover both Turbo and debug. A legacy
system Ollama using this project's models was stopped after ownership proof;
subsequent starts/stops used the already configured user service. No service
configuration or model files were replaced.

## Memory observation

Same local Full installation, dev/Turbo, same saved Ollama model selection,
chat metadata only, no loaded LLM weights or generated turns in either sample.
PSS includes the listener and its descendants; figures are rounded MiB.

| Process group | Venom | Studio |
| --- | ---: | ---: |
| UI/proxy | 455.2 | 564.5 |
| API | 2466.2 | 172.7 |
| Ollama server, no loaded model | 35.2 | 35.4 |
| Total | 2956.6 | 772.6 |

The observed total dropped by about 2.13 GiB (74%), chiefly in API startup.
The development web alone did not improve in this sample. Whole Windows RAM
snapshots were 25.22 and 23.57 GiB used; background work, WSL caching and browser
state prevent treating that difference as a controlled application benchmark.

These are idle/startup observations, not steady-state chat/voice benchmarks.
Existing Direct memory ingestion, Normal/MAF and first audio use can initialize
shared heavier services and increase RAM/VRAM. They retain the original behavior;
this work does not add a new RAG, training mode or diagnostic screen.

Live provider test zero, real microphone, robot actions, a separate Light
installation and full preprod/prod qualification remain outside this acceptance.
A passive browser reported only an unrelated missing favicon; no application
or hydration error was observed. Rider initialization remains a separate repair.
