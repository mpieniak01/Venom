# External model providers

Implemented on `codex/openrouter-chat-mvp`:
1. Decouple application startup from remote API availability. Retain selected remote identity and reject only generation; never silently fall back.
2. Add persistent operator enable/disable controls and explicit metadata-only connection checks for OpenRouter and VAST.
3. Extend Models → Remote models with provider cards, catalogs, selection and independent enabled/configured/available/selected states.
4. Expose the existing VAST environment lifecycle in Models → VAST, with an explicit paid-order confirmation. API enable/disable never stops, destroys or rents a host.
5. Verify startup, unavailable/disabled APIs, selection preservation and recovery using offline fixtures, then run `make pr-fast`.

## Operator flow

OpenRouter: configure the existing secret injection and budgets; enable the API and check authentication in Remote models. In the dedicated OpenRouter tab, search and connect one or more models. Then choose a connected model in the chat selector. Connecting never changes the active model. Checking only calls the key metadata endpoint and does not generate text. Enabling does not change the current model. Cloud policy and budget checks still apply.

VAST: open Models → VAST, search for an eligible host and review the quote before explicitly ordering it. The worker provisions the configured model and attaches it after metadata readiness. Choose VAST and that model explicitly in chat. Remote models provides API enable/disable and connection status; the infrastructure link opens the VAST tab. Advanced manual attachment of an existing managed plan remains available by its 32-character plan ID. Detach disconnects transport while retaining the selected identity. API enable does not rent, install, attach or start a host; API disable does not stop billing for infrastructure.

Controls persist at `.venom_runtime/remote-providers/control.json`. No secrets are stored there. A corrupt control file disables API use until repaired. OpenRouter defaults to its existing OPENROUTER_ENABLED setting; VAST retains legacy enabled behavior until explicitly disabled. Existing service credentials are never exposed to the UI.

An offline or disabled selected provider remains selected. Venom can start and expose administrative UI; a new model invocation fails explicitly for that provider. In-flight calls may complete. Check status separately from selecting a model. Unknown reachability before the first check must not be displayed as authenticated.

See [VAST provisioning and environment lifecycle](integrations/vast.md) for the existing host preparation, installation, qualification and cleanup workflow. The integration configuration link is diagnostic/configuration UI, not a rental console.

VAST retrieves up to 1000 candidates per global/preferred-country metadata query
before local qualification and deduplication. Each search reads qualification
history and computes the workload identity once; standalone assessments still
read fresh history. This remains a bounded catalog
sample, not a guarantee of every marketplace offer.
VAST offer search displays only eligible offers with known nonnegative hourly
and total quotes. It sorts by the exact hourly rate ascending before limiting
results to 100; equal rates use offer ID for stable ordering. Offers, order reviews
and managed environments display USD amounts rounded to four decimal places.
The “Exact USD amounts” disclosure in each offer and the order review exposes
unrounded prices for budget entry. Quote validation, budget limits and order
requests retain full precision. Existing
environments and historical attempts remain visible regardless of eligibility.

## OpenRouter model connections

The dedicated OpenRouter tab searches provider metadata by name/ID, chat/task/programming profile and category. Tools indicate task candidates, not coding-agent qualification. Discovery and connecting use metadata GET requests only. Explicit connect pins a compatible endpoint and validated prices under existing budgets. Unknown prices and dynamic aliases cannot be connected.

The search checkbox “Free models only” sends `max_price=0` and
`max_output_price=0` to the OpenRouter models API. Venom also validates zero
prompt, completion and request prices before pagination; unknown prices are
excluded. A missing request rate is accepted only for fixed `:free` variants.
The filter does not change connected models or generate text.

Connections persist in `.venom_runtime/openrouter/connected-models.json` (up to 100 fixed IDs). Legacy shortlist is read only until this registry exists. Disconnecting the last model leaves an empty registry. Prices expire individually after 24 hours; refresh an unavailable connected model in the tab. Connecting another model does not refresh old prices or change the selected model's quote identity.

Disconnecting an active model retains its identity but blocks its next request; in-flight generation may finish. Other connections remain available. Provider enable/disable stays in Remote models.

## Local acceptance

Tests use mocked transports and an isolated network namespace. No live API generation or infrastructure operation is required. Feature source remains on the existing branch until a separate deployment/review decision.

## Manual provider test zero

VAST and OpenRouter test zero are manual acceptance operations only on an explicit operator request for that run. They are excluded from automatic test policies, startup and post-change checks. Metadata checks and model connections never trigger generation. Automated tests of their code use only doubles. See [policy](PROVIDER_TEST_ZERO_POLICY.md) ([PL](PL/PROVIDER_TEST_ZERO_POLICY.md)).

## VAST management tab

Open **Models → VAST** (`/models?tab=vast`). The server loads one reviewed Ollama
profile from `VAST_CHAT_PROFILE_FILE`; the local default is the existing prepared
`chat-gemma4-26b-q4-24gb.json` under `.venom_runtime/vast/prepared/`. The profile
pins the image and model digests, download allowance and hardware requirements.
SSH uses the existing private `secrets/ssh/vast/connection.json`; the browser
never supplies executable recipes, filesystem paths, credentials or SSH options.

1. Search offers for the selected estimated duration and choose an eligible host.
2. Set maximum hourly and estimated total USD, then prepare a time-limited quote.
3. Review it and explicitly confirm the paid order. First-use SSH trust is a
   separate opt-in (`accept-new`); changed host keys remain rejected.
4. The background job creates one rental, waits for SSH, checks capacity, installs
   the pinned model and opens the managed tunnel. Matching API/model metadata
   automatically marks VAST connected in Remote Models. No generation is sent.
5. In chat select **VAST · Ollama**, then the installed model. Attachment does not
   change the active provider or model; normal runtime selection remains explicit.
6. Stop or destroy from the environment row. Stopped hosts may still incur storage
   charges. The billing column shows a recorded provider amount or a compact
   status; destruction does not establish that earlier charges were zero. Setup currently completes or fails before cleanup actions
   become available; interrupted, never-submitted orders can be cancelled safely.

Cost caps validate the rental quote, including the declared transfer allowance;
they are not an ongoing spending meter or an automatic destruction timer. Failed
setup retains the rented host for operator recovery/cleanup. Unknown create outcomes
are reconciled without retrying the paid create call. API restart never re-rents or
automatically provisions: use the row's refresh to reattach a previously provisioned
order, or clean up an interrupted setup. Disabling the provider prevents setup/attach
and generation, while cleanup remains available. Missing VAST configuration or an
unavailable external API never blocks Venom startup.

This workflow does not invoke `ready`, benchmarks or `trial-zero`: those can generate
model output. Real Test Zero remains a separate manual operator-request-only action.


### Billing statuses in VAST

The overview reads the provider charge report already saved by the existing
VAST CLI `costs` operation. It does not query billing when opening or refreshing
the page. `Reported` displays the saved USD amount, including an explicit zero;
`Unavailable` means the saved billing query was unavailable, `Unverified` means
there is no usable provider amount, and `Not applicable` identifies a plan that
has never been submitted. Quotes and estimates are never displayed as charges.
