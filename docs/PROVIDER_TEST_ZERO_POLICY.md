# Provider test zero — operator request only

This policy applies to both VAST (`trial-zero`) and OpenRouter (`scripts/cloud/openrouter/test_zero.py`). It governs real provider connections, model replies and any VAST infrastructure operations performed as part of test zero.

A real test zero is a manual acceptance action, executed only on the operator's explicit request for that run. Available credentials, an approved budget, connected models, a previous successful run or completion of development do not authorize another run. Existing provider budget and infrastructure approval requirements still apply.

Do not include real test zero in local PR gates, `make pr-fast`, unit/integration regression policies, GitHub Actions, Sonar, scheduled jobs, startup, deployment hooks or automatic post-change verification. Enabling a provider or connecting a model must not trigger it. An unavailable external provider or absence of a manual test-zero result must not block Venom startup or automated code-quality gates.

Automated unit/contract tests may verify the test-zero implementation using fake transports and provider doubles only. These are tests of code, not an executed provider test zero. `tests/test_openrouter_test_zero.py` and the VAST cleanup/zero tests exercise such doubles; their presence in a test catalog does not authorize live API calls, rentals or generation.

Ordinary provider status, model discovery and the explicit connection-check controls remain separate product operations. A metadata-only check must never be reported as successful end-to-end test zero or silently upgraded to model generation.

When requested, record the actual manual scope, revision/configuration, provider/model or VAST plan, outcome and reported cost separately from CI results. A mocked test pass is not evidence of a real response. Do not provision VAST resources, switch the operator's active model, or repeat an ambiguous generation beyond the requested scope.
