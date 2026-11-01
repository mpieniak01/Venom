# PR56 Model selection and Direct chat acceptance

## Integration on current main (2026-11-01)

Integration branch: codex/pr56-main-integration, based on origin/main
630bfe8b795481bc2b5968bb653cf09d41d56c6e. The five original PR56 files are
ported, with two registry implementation/test files for compatibility;
the old branch's nine inherited commits are not merged wholesale.
The current main's material handling, runtime guard, registry and provider
max_price limits are retained. Optional ZDR uses the shared catalog-row
validator, including connected registry entries. Its default false is part
of config_hash only when enabled. Omitted/false preserves the main catalog
identity and the working selection; enabling it invalidates the old quote.
Metadata refresh preserves an explicit operator policy, including opt-in.
Four fail-first compatibility cases cover both behaviors (omitted/false
selection identity, and false/true policy retention on registry refresh).

The results below are historical acceptance of the isolated PR56 branch,
not live acceptance of this new main base or deployment. Full live UI STOP,
cost drawer and full-API acceptance remain open. No provider calls or live
service changes are part of this integration. Retain the old worktrees:
they hold ignored receipts and the existing venv used by local validation.

## Historical PR56 acceptance

Current acceptance: changing to cohere/north-mini-code:free / Cohere passed
two real turns through the actual core 0.2.0 adapter, history recall and
confirmed zero USD accounting (two settled reservations). One selection,
two HTTP 200 POSTs, no retry/ZDR lookup or account changes. Sources unchanged
at 699e9129; report .venom_runtime/pr56-live-cohere-20261101/report.json,
SHA256 5abf15ccaf0d8e329a7cbd1c9257f82dbae17ff96e83a8875a7ef5ff5e92aa44.
Earlier failed runs and pending rows remain historical evidence below.

Next stage executed: 15 UI logic and 19 component tests PASS using existing
dependencies, covering quote STOP, history/runtime isolation, failure/pending
and accounting display. This does not claim a live-browser E2E or deployment.
Continue with live UI acceptance; model selection/connection is no longer open.

Scope: explicit operator selection of a paid model is consent to use that
model for the requested work within the configured budget. Do not add a
second approval per quote, message or HTTP request. An explicit instruction
to choose within configured caps also suffices. A fallback without that
instruction is not an operator choice. Price/config identity, LOCAL, STOP,
pending reservations and limits remain enforced; selection is not deployment
or hardware authorization.

The existing UI already quotes automatically before send. No extra consent
API, checkbox, provider setting or runtime mutation is introduced. New tests
use the installed core 0.2.0 with a fake HTTP transport and positive pricing:
two turns after one selection, durable settlement, and pending spend blocking
a later turn before network dispatch.

Base: 57ff8af2, isolated branch codex/pr56-model-selection-consent.
No production checkout/service, credentials or budget state is modified.
Targeted acceptance: Ruff PASS; 44 runtime/wheel tests PASS (0.66 s), using
the installed wheel 0.2.0 and mocked transport. This does not claim live UI
acceptance. Runtime snapshot: the existing comparison stack has OpenRouter
disabled and no selected model; it was not changed.

The operator authorized free models or paid models within the existing
USD 0.01/message, 0.03/conversation and 0.10/day caps. Two isolated real
attempts used only free fixed endpoints: Liquid LFM2.5 (HTTP 404) and
Xing4.0 through Phala (stream failed). Each sent one POST, with no retry,
client fallback or second turn after error. Real HTTP, public quote/simple
routes, installed core 0.2.0 and runtime/admission guards were retained.
The Phala endpoint was checked against OpenRouter's public ZDR list.

Neither attempt is accepted: no completed two-turn interaction and no
confirmed upstream usage/cost. Both receipts and pending reservations are
retained. A zero tariff/estimate is not confirmed zero spend. No paid
model, main deployment, global provider or live UI configuration was changed.
Evidence: .venom_runtime/pr56-live-20261101 and pr56-live-zdr-20261101.
Next: diagnose transport/SSE safely, reproduce offline, then perform bounded
multiturn and live UI/STOP/session acceptance. Consent is already established;
do not add another payment-approval surface.

## Optional ZDR

Operator follow-up: ZDR is an option, not a mandatory model-selection gate.
Each approved catalog row may set zdr_required (boolean, default false).
Only true adds provider.zdr=true; false/omitted does not read or filter the
public ZDR list. Account/guardrail restrictions cannot be overridden by this
flag and are not changed by the application. The separate existing
data_collection=deny filter is unchanged.

The optional flag is validated; enabled policy is bound to config_hash and
the quote. Toggling it invalidates an old captured selection, but omitted
and false have the same default identity as main. LOCAL, cost caps,
pending, exact model and no retry remain unchanged. The new synthetic test
uses false, a fresh run directory and no ZDR-list lookup; old evidence stays.
Capture a fresh selection/quote only if its configuration changed; this is
not a second business consent. Preserve budgets and default main selections.

Follow-up retest: one real POST to the fixed free Xing4.0/Phala endpoint,
with zdr_required=false and no ZDR-list lookup or provider.zdr field. It was
rejected with HTTP 429 before an SSE stream. No second turn or retry, no
confirmed usage/cost; the zero estimate remains pending, not settled zero.
GET /key succeeded; the available metadata does not establish why this
endpoint returned 429. Evidence: .venom_runtime/pr56-live-optional-20261101.
The two previous report hashes and reservations were preserved unchanged.

Optional-ZDR implementation: dfea3354. Targeted tests 50 PASS, fresh installed
wheel qualification 101 PASS, CI-lite 895 PASS and pr-fast 1159 PASS.
Changed lines: 5/5 (100%, required 80%) against the exact follow-up base
0afd394c; coverage floors passed for 14 files. No frontend/main deployment
acceptance is implied. Logs: .venom_runtime/pr56-zdr-optional-checks-20261101.
