# External model providers

Implementation plan on `codex/openrouter-chat-mvp`:
1. Decouple application startup from remote API availability. Retain selected remote identity and reject only generation; never silently fall back.
2. Add persistent operator enable/disable controls and explicit metadata-only connection checks for OpenRouter and VAST.
3. Extend Models → Remote models with provider cards, catalogs, selection and independent enabled/configured/available/selected states.
4. Retain VAST infrastructure lifecycle in the existing integrations/environment tools. Disabling API access never stops, destroys or rents a host.
5. Verify startup, unavailable/disabled APIs, selection preservation and recovery using offline fixtures, then run `make pr-fast`.

## Operator flow

OpenRouter: configure the existing secret injection, approved model shortlist and budgets; enable the API in Remote models, check authentication, then choose a model. Checking only calls the key metadata endpoint and does not generate text. Enabling does not change the current model. Cloud policy and budget checks still apply.

VAST: use the existing VAST integration to prepare a host/environment, install the engine/model and qualify the API. Attach the prepared plan through the existing VAST connection operation. Remote models then manages API access and selection. The infrastructure link opens the existing integrations panel. API enable does not rent, install, attach or start a host; API disable does not stop billing for infrastructure.

Controls persist at `.venom_runtime/remote-providers/control.json`. No secrets are stored there. A corrupt control file disables API use until repaired. OpenRouter defaults to its existing OPENROUTER_ENABLED setting; VAST retains legacy enabled behavior until explicitly disabled. Existing service credentials are never exposed to the UI.

An offline or disabled selected provider remains selected. Venom can start and expose administrative UI; a new model invocation fails explicitly for that provider. In-flight calls may complete. Check status separately from selecting a model. Unknown reachability before the first check must not be displayed as authenticated.

## Local acceptance

Tests use mocked transports and an isolated network namespace. No live API generation or infrastructure operation is required. Feature source remains on the existing branch until a separate deployment/review decision.
