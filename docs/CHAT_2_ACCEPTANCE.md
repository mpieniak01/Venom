# Chat 2.0 — local acceptance, 2026-10-31

Implementation branch: `codex/group-b-venom-chat-2`. Code reviewed and browser-tested:
`ce53320e02ece3a821a28a64524261c26eba8c34`. Base: `e01e7b08ed1797dbc84803b5944515db626e16d4`
(Group A, merged PRs 571/570/572). Later documentation commits do not change this code.

## Outcome and rollout

At the time of this local acceptance, B01–B06 were implemented and B07 local
functional, visual and frontend observations were accepted. This was **local
acceptance, not a GitHub release**: no Group B PR had been published and GitHub
CI/SonarCloud had not run for this branch. The operator's running stack remained
on its existing main revision/configuration.
`NEXT_PUBLIC_FEATURE_CHAT2=false` is retained in templates; enable deliberately
according to [the operator guide](CHAT_2.md). Disabling it preserves history,
drafts and materials and returns operators to `/chat`.

The accepted Studio shell uses the existing Next.js/FastAPI deployment and shared
conversation controller, runtime admission, history and transport. It does not
mount the old console chrome, metrics, graph or Git polling. Other application
URLs remain available through the existing console route group.

## Implemented boundaries

- Text/history, model selection, runtime identity, costs, Direct/Normal/MAF where
  supported, streaming, scoped Stop, partial output and reload recovery.
- Session-owned TXT/MD/CSV/JSON references and validated local Ollama vision
  images. Unknown prices are not shown as free. Remote image execution/accounting,
  PDF/Office extraction, native model audio and video remain unavailable.
- Explicit dictation edits a draft; manual voice turns use existing STT, the same
  text controller and TTS. No microphone, model load or paid generation at entry.
- Desktop/mobile, PL/EN/DE, shared themes, labelled keyboard controls, Escape/focus
  restoration, a visible mobile composer and optional materials overlay.

## Executed checks

| Command / procedure | Result |
| --- | --- |
| `make pr-fast` | PASS; 1,322 selected Python tests, frontend unit suite and 342 component tests; changed-line coverage **93.01%**, minimum 80%; all 14 per-file floors pass. |
| `make test-ci-lite` | PASS; 898 tests. |
| `make test-web-unit` | PASS; complete maintained non-component web unit suite. |
| `npm --prefix web-next run test:unit:components` | PASS; later repeated by final pr-fast, 342 tests. |
| `npm --prefix web-next run lint` | PASS; zero warnings. |
| `cd web-next && npx --offline tsc --noEmit` | PASS. |
| `npm --prefix web-next run lint:locales` | PASS; PL/EN/DE parity. |
| `mypy venom_core` | PASS; 474 source files. |
| `make test-catalog-check test-groups-check check-new-code-coverage-diagnostics` | PASS; 544 catalogued files, synchronized groups and actual generated coverage. |
| `make openapi-export` and pinned offline `openapi-typescript@7.10.1` | PASS; new chat paths/schemas reflected in contract and generated TS. Unrelated historical paths retained. |
| Playwright CLI, Windows Chrome, fake API/audio | PASS; **58 assertions**, no skipped scenario. |
| Normal pre-commit hooks on commits, `git diff --check` | PASS. |

The generic full live-provider e2e profile was not executed. The browser suite
instead runs the committed `tests/chat2-acceptance.mjs` against an isolated UI
whose API proxy targets a closed local port. All API/audio writes are explicit
in-browser fakes, including STT/TTS and task streams. This is not a live API or
microphone qualification; no physical robot or paid provider was contacted.

Browser evidence includes owned-ID material upload/preview, rejection preserving
its draft, delayed ACK preserving newer edits, Stop retaining partial output,
return/reload with material history, exact Normal UUID reattachment, terminal
unlock, two-session isolation, 240-message history with 60/120 mounted messages,
repeated voice cycles, both themes, mobile geometry and Escape/focus restoration.
There were zero external attempts/unexpected writes/uncaught/hydration errors;
4 fake microphone tracks and 4 AudioContexts were created and all released,
playback was stopped and its object URL revoked. The separate Next dev HMR
connection was allowed only for the test UI's exact local origin and HMR paths.

## Frontend observations in the same development server

Node 24.22.0, Next 16.4.2, Turbopack, desktop 1440×1000, fresh Chrome context per
sample, HTTP cache disabled, fake API/audio, browser heap after explicit GC.
Three visits per route, alternating order; table medians use the last two visits.
Routes were compiled before this series, so the fixture field `coldCompilation`
on its first round does **not** represent a measured cold process/cache start.
The comparison is the existing `/chat` route and `/chat2` at the candidate code,
not a separate run of Group A's exact binary and not dev-versus-production.

Both routes had their complete renderer visible, no error boundary, and valid
GET shapes (in particular `/tasks` is an array). The first exploratory run with
an invalid legacy task envelope was rejected and is not used in this table.

| Observation | `/chat` | `/chat2` |
| --- | ---: | ---: |
| Initial fake API GET calls in observation window | 32 | 10 |
| JS resources | 27 | 21 |
| JS decoded size | 7.14 MiB | 4.81 MiB |
| JS transfer size incl. resource overhead | 1.27 MiB | 1.00 MiB |
| JS heap after GC | 15.33 MiB | 9.80 MiB |
| DOM elements | 889 | 158 |
| Visible renderer + initiated session GET | 983 ms | 426 ms |

These short observations establish route isolation and reduced browser work;
they do not establish production performance, model TTFT, real STT/TTS latency
or whole-stack RAM savings. Two warm samples are insufficient for p95.
Legacy external daemon attempts were blocked by the fixture; Studio made none.
Both routes made zero real provider calls and requested no real microphone.

The isolated shared Next/proxy process tree after both routes compiled measured
790,598 KiB PSS (about 772.1 MiB). This includes dev compilation/workers and both
routes; it cannot be attributed to a route or subtracted from API/LLM memory.
The existing API/model/profile was not restarted or re-profiled for this report.

## Internal review and limits

Independent review found three P2 issues and no P1: ACK removing newer edits
(in both composers), Normal streams crossing conversation boundaries, and stale
Direct cache hiding a terminal server turn. All were fixed with regressions.
The final reviewed code has no remaining confirmed P1/P2 in that review scope.
The browser run additionally verified the assistant-only terminal recovery guard
and mobile controls without forced clicks.

Real microphone/browser-device interoperability, speech/model quality, real
provider Test Zero and live image inference were deliberately not run. Existing
audio services and quality settings were retained; fake success is not a quality
claim. Rider initialization remained a separately deferred task. At that time,
GitHub required checks and SonarCloud qualification remained prerequisites for
publishing/merging the branch. Subsequent release qualification is recorded in
[PR #574](https://github.com/mpieniak01/Venom/pull/574).

[Polish operator guide](PL/CHAT_2.md) · [ADR-003](adr/ADR-003-chat-2-shell.md)
