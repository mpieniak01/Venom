# OpenRouter Direct chat: local qualification

OpenRouter is a distinct, opt-in cloud runtime for the existing cockpit. The default is disabled. This local increment implements Direct text chat; Normal/MAF, tools and automatic model fallback are unavailable. No real provider or paid pilot is certified by offline tests.

## Shared package

The independently versioned `agent-execution-core` wheel comes from the local orchestration repository. Its `release.json` records package version, source commit and SHA256. Verify the receipt before installing. The application imports the installed distribution and never imports another repository's source directory. Use the existing Python environment. Local qualification installs into a temporary target, leaving the running application untouched.

The private wheel is not currently available to GitHub runners. Public CI exercises provider-boundary tests using injected transport/library boundaries. `tests/test_openrouter_wheel.py` explicitly reports that the local artifact is required unless the local acceptance gate enables it. The paired-repository receipt is required for full integration acceptance.

```bash
source .venv/bin/activate
python scripts/qualify_openrouter_local.py --wheel /path/to/package.whl --receipt /path/to/release.json --windows-proof /path/to/qualification-windows.json
```

Run this in the approved isolated test environment. The Windows receipt must include the same wheel and successful package plus orchestration regression groups. The gate verifies SHA256, installs without network/dependencies into a temporary directory, checks import origin and runs Venom's actual-wheel acceptance. Retain the receipt and logs alongside the two consumer commits.

## Configuration and activation

Before a separately authorized live pilot, configure `OPENROUTER_MODELS_FILE` with an operator-approved shortlist (one to three exact model IDs). Its JSON object contains `pricing_as_of` (timezone-aware ISO time, at most 24 hours old) and `models`. Each row requires `id`, `provider_endpoint`, `context_length`, `max_output_tokens`, and `pricing` with explicit `prompt`, `completion`, `request` rates in USD/token or USD/request as returned by the provider. Missing prices are unavailable, not free. Auto/latest aliases are refused. Catalog refresh is explicit and external to normal chat; opening the page does not query OpenRouter.

The following settings default to disabled/zero: `OPENROUTER_ENABLED`, `OPENROUTER_MESSAGE_LIMIT_USD`, `OPENROUTER_CONVERSATION_LIMIT_USD`, `OPENROUTER_DAILY_LIMIT_USD`. Supply approved limits before a pilot. `OPENROUTER_LIBRARY_VERSION` pins the installed distribution. Cloud policy requires `AI_MODE=HYBRID` or `CLOUD` and `SENSITIVE_DATA_LOCAL_ONLY=false`; selecting the runtime does not weaken those settings.

Credentials are supplied through `OPENROUTER_API_KEY` or a private `OPENROUTER_CREDENTIAL_FILE`. The optional Windows helper `scripts/Invoke-OpenRouterCredentialBridge.ps1` transfers the existing process/user OpenRouter key over stdin to the Linux helper. It writes only inside ignored `.venom_runtime` with private permissions; it does not enable the runtime or change budgets. Configure the file path explicitly. No key belongs in a wheel, UI, report or configuration hash.

Select OpenRouter using the existing runtime/model selector. `/api/v1/openrouter/status` and `/catalog` provide offline configuration metadata. Presence of a credential is not authentication evidence. Quotes use `/api/v1/openrouter/quote` without reserving funds or invoking a model. A Direct request must include the matching `expected_runtime_id`, `expected_config_hash`, `expected_quote_hash`, and provider-scoped `session_id`. Changes to history, model, parameters or pricing invalidate the quote.

## Billing and STOP

Quotes conservatively bound serialized input and maximum output; they are not reported token usage. SQLite reservations are atomic and survive restart. A single admitted request performs one POST to the fixed HTTPS OpenRouter endpoint, with one provider and no fallback/retry. Stream errors after HTTP200, incomplete EOF, total deadline expiry and cancellation retain uncertain usage as pending. A zero-priced estimate is still distinct from reported zero cost. UI shows per-turn and conversation reported/held values, real usage when present, and requested/confirmed model/provider/generation identity.

STOP cancels the client's quote or response and closes the application's upstream request. It does not certify immediate cessation of provider billing. Pending reservations need reconciliation from confirmed provider accounting; restarting or changing the selected model does not erase them. Rollback disables the feature, selects a local runtime explicitly, and preserves accounting state.
