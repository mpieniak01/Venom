# External model providers

Implementation plan on `codex/openrouter-chat-mvp`:
1. Decouple application startup from remote API availability. Retain selected remote identity and reject only generation; never silently fall back.
2. Add persistent operator enable/disable controls and explicit metadata-only connection checks for OpenRouter and VAST.
3. Extend Models → Remote models with provider cards, catalogs, selection and independent enabled/configured/available/selected states.
4. Retain VAST infrastructure lifecycle in the existing integrations/environment tools. Disabling API access never stops, destroys or rents a host.
5. Verify startup, unavailable/disabled APIs, selection preservation and recovery using offline fixtures, then run `make pr-fast`.

## Operator flow

OpenRouter: configure the existing secret injection and budgets; enable the API and check authentication in Remote models. In the dedicated OpenRouter tab, search and connect one or more models. Then choose a connected model in the chat selector. Connecting never changes the active model. Checking only calls the key metadata endpoint and does not generate text. Enabling does not change the current model. Cloud policy and budget checks still apply.

VAST: use the existing VAST integration to prepare a host/environment, install the engine/model and qualify the API. In Remote models, enter the prepared 32-character plan ID and use Attach API. Detach API disconnects transport while retaining the selected identity. Neither action activates a model or changes infrastructure billing. Remote models then manages API access and selection. The infrastructure link opens the existing integrations panel. API enable does not rent, install, attach or start a host; API disable does not stop billing for infrastructure.

Controls persist at `.venom_runtime/remote-providers/control.json`. No secrets are stored there. A corrupt control file disables API use until repaired. OpenRouter defaults to its existing OPENROUTER_ENABLED setting; VAST retains legacy enabled behavior until explicitly disabled. Existing service credentials are never exposed to the UI.

An offline or disabled selected provider remains selected. Venom can start and expose administrative UI; a new model invocation fails explicitly for that provider. In-flight calls may complete. Check status separately from selecting a model. Unknown reachability before the first check must not be displayed as authenticated.

See [VAST provisioning and environment lifecycle](integrations/vast.md) for the existing host preparation, installation, qualification and cleanup workflow. The integration configuration link is diagnostic/configuration UI, not a rental console.

## OpenRouter model connections

The dedicated OpenRouter tab searches provider metadata by name/ID, chat/task/programming profile and category. Tools indicate task candidates, not coding-agent qualification. Discovery and connecting use metadata GET requests only. Explicit connect pins a compatible endpoint and validated prices under existing budgets. Unknown prices and dynamic aliases cannot be connected.

Connections persist in `.venom_runtime/openrouter/connected-models.json` (up to 100 fixed IDs). Legacy shortlist is read only until this registry exists. Disconnecting the last model leaves an empty registry. Prices expire individually after 24 hours; refresh an unavailable connected model in the tab. Connecting another model does not refresh old prices or change the selected model's quote identity.

Disconnecting an active model retains its identity but blocks its next request; in-flight generation may finish. Other connections remain available. Provider enable/disable stays in Remote models.

## Local acceptance

Tests use mocked transports and an isolated network namespace. No live API generation or infrastructure operation is required. Feature source remains on the existing branch until a separate deployment/review decision.

## Manual provider test zero

VAST and OpenRouter test zero are manual acceptance operations only on an explicit operator request for that run. They are excluded from automatic test policies, startup and post-change checks. Metadata checks and model connections never trigger generation. Automated tests of their code use only doubles. See [policy](PROVIDER_TEST_ZERO_POLICY.md) ([PL](PL/PROVIDER_TEST_ZERO_POLICY.md)).
