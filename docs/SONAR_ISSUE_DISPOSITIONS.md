# Reviewed Sonar issue dispositions — 19 October 2026

Review baseline: main `fabce6b322a6884ad938c98688e93dfe6f0eb638`, after PRs #547–#550.
The analysis closed 729 of the original 742 findings through code changes. This
ledger covers the remaining 13 maintainability findings: **9 false positives and
4 accepted design/formatting deviations**. None is a vulnerability or a functional
fix. Accepted findings must not be reported as code-fixed or false-positive.

Each decision applies only to the named issue and the reviewed code. Record its
rationale as an individual Sonar comment and transition; do not disable rules,
add NOSONAR, suppress files or lower quality gates. Reopen the decision when its
listed trigger applies, even if Sonar retains a previous disposition after edits.

## Individual decisions


### `AaFPyhJzzI2nLJqFU1QL` — python:S100

Source: `venom_core/execution/agent_contracts.py:77`. Decision: **Accepted**.

ToolPolicy.Auto is an existing public classmethod constructor used by runtime callers and tests. Auto intentionally preserves the established compatibility contract. Renaming it would break those callers; adding a second constructor only to satisfy this naming rule expands the API without functional benefit. The naming deviation is acknowledged, not classified as a false positive.

Validation: tests/test_maf_runtime.py; tests/test_llm_server_selection.py.

Revisit: Re-review during a deliberate versioned public API migration with caller compatibility tests.

### `AaFPyg0uzI2nLJqFU1QC` — python:S7483

Source: `venom_core/services/system_llm_service.py:106`. Decision: **Accepted**.

inspect_onnx_worker forwards timeout to httpx.AsyncClient for connect/read/write/pool inactivity limits on the sequential health and model-catalog requests. This is not a total-operation deadline. Replacing that setting with one asyncio.timeout context changes phase budgets, exception mapping and cancellation semantics. Keep the public timeout keyword and offline handling; callers can independently impose an outer deadline. This is an acknowledged design exception.

Validation: tests/test_system_llm_service.py; tests/test_llm_server_selection.py; HTTPX timeouts documentation.

Revisit: Re-review when explicitly redesigning the probe contract to separate HTTPX phase limits from an overall caller deadline.

### `AaE0MsKGKC7JPIdEUCH6` — typescript:S9382

Source: `web-next/lib/api-client.ts:88`. Decision: **False positive**.

Response parsing must settle inside the current retry try/catch before deciding whether another GET attempt is allowed. return await deliberately catches an asynchronous body-read TypeError; returning the promise directly would bypass that retry boundary. Attempts are dependent and bounded, an explicit exception in the S9382 rule.

Validation: web-next/tests/api-client-retry.test.ts; web-next/tests/multi-runtime-readiness.component.test.tsx.

Revisit: Re-review if the loop changes to independent batch operations or loses its attempt/deadline/unmount bounds.

### `AaE0MsKGKC7JPIdEUCH7` — typescript:S9382

Source: `web-next/lib/api-client.ts:98`. Decision: **False positive**.

This is a bounded retry backoff after a failed GET, not independent work. Waiting 200 ms / 500 ms must finish before the next dependent attempt; parallel promises would remove backoff and could replay operations incorrectly. POST is not retried. Sequential retries are an explicit exception in S9382.

Validation: web-next/tests/api-client-retry.test.ts; web-next/tests/multi-runtime-readiness.component.test.tsx.

Revisit: Re-review if the loop changes to independent batch operations or loses its attempt/deadline/unmount bounds.

### `AaE0MsOsKC7JPIdEUCIH` — typescript:S9382

Source: `web-next/hooks/use-multi-runtime-profile.ts:66`. Decision: **False positive**.

Each daemon-readiness poll depends on the preceding result and waits 1000 ms only while the daemon is not ready. The update/reload is performed once, not replayed by the loop. Parallelizing delays or polls changes readiness, resource use and timeout behavior. Dependent sequential operations are an explicit exception in S9382.

Validation: web-next/tests/api-client-retry.test.ts; web-next/tests/multi-runtime-readiness.component.test.tsx.

Revisit: Re-review if the loop changes to independent batch operations or loses its attempt/deadline/unmount bounds.

### `AaFQfCpfYI9SFDyzCT3E` — python:S1110

Source: `venom_core/services/academy/adapter_runtime_service.py:897`. Decision: **False positive**.

The single pair groups a multi-line string expression using Python implicit line continuation. It is not a redundant nested pair. Removing it without replacing the continuation is invalid syntax; flattening or adding backslashes would conflict with the maintained readable layout. The current file passes Ruff formatting.

Validation: ruff format --check (8 files); parentheses-evidence.json (AST and formatter round-trip).

Revisit: Re-review if the expression becomes single-line or gains a genuinely redundant nested pair.

### `AaFQfCkLYI9SFDyzCT3A` — python:S1110

Source: `venom_core/agents/apprentice.py:498`. Decision: **False positive**.

The single pair groups a multi-line string expression using Python implicit line continuation. It is not a redundant nested pair. Removing it without replacing the continuation is invalid syntax; flattening or adding backslashes would conflict with the maintained readable layout. The current file passes Ruff formatting.

Validation: ruff format --check (8 files); parentheses-evidence.json (AST and formatter round-trip).

Revisit: Re-review if the expression becomes single-line or gains a genuinely redundant nested pair.

### `AaFQfDRoYI9SFDyzCT3c` — python:S1110

Source: `venom_core/execution/skills/test_skill.py:195`. Decision: **False positive**.

The single pair groups a multi-line string expression using Python implicit line continuation. It is not a redundant nested pair. Removing it without replacing the continuation is invalid syntax; flattening or adding backslashes would conflict with the maintained readable layout. The current file passes Ruff formatting.

Validation: ruff format --check (8 files); parentheses-evidence.json (AST and formatter round-trip).

Revisit: Re-review if the expression becomes single-line or gains a genuinely redundant nested pair.

### `AaFQfDY1YI9SFDyzCT3f` — python:S1110

Source: `venom_core/core/orchestrator/orchestrator_flows.py:242`. Decision: **False positive**.

The single pair groups a multi-line string expression using Python implicit line continuation. It is not a redundant nested pair. Removing it without replacing the continuation is invalid syntax; flattening or adding backslashes would conflict with the maintained readable layout. The current file passes Ruff formatting.

Validation: ruff format --check (8 files); parentheses-evidence.json (AST and formatter round-trip).

Revisit: Re-review if the expression becomes single-line or gains a genuinely redundant nested pair.

### `AaFQfDQVYI9SFDyzCT3Z` — python:S1110

Source: `venom_core/execution/skills/google_calendar_skill.py:375`. Decision: **Accepted**.

The pair is semantically optional for this single string expression, so this is accepted formatting debt, not a false positive. Flattening preserves the AST, but the configured Ruff formatter restores the exact pair because of line length. Retain formatter consistency rather than add a temporary variable, a formatter suppression or an overlong line solely for this finding.

Validation: ruff format --check (8 files); parentheses-evidence.json (AST and formatter round-trip).

Revisit: Re-review if the message, indentation or formatter policy changes so that a single-line expression is retained.

### `AaFQfCZTYI9SFDyzCT29` — python:S1110

Source: `venom_core/agents/system_status.py:60`. Decision: **False positive**.

The single pair groups a multi-line string expression using Python implicit line continuation. It is not a redundant nested pair. Removing it without replacing the continuation is invalid syntax; flattening or adding backslashes would conflict with the maintained readable layout. The current file passes Ruff formatting.

Validation: ruff format --check (8 files); parentheses-evidence.json (AST and formatter round-trip).

Revisit: Re-review if the expression becomes single-line or gains a genuinely redundant nested pair.

### `AaFQfDRPYI9SFDyzCT3a` — python:S1110

Source: `venom_core/execution/skills/chrono_skill.py:182`. Decision: **False positive**.

The single pair groups a multi-line string expression using Python implicit line continuation. It is not a redundant nested pair. Removing it without replacing the continuation is invalid syntax; flattening or adding backslashes would conflict with the maintained readable layout. The current file passes Ruff formatting.

Validation: ruff format --check (8 files); parentheses-evidence.json (AST and formatter round-trip).

Revisit: Re-review if the expression becomes single-line or gains a genuinely redundant nested pair.

### `AaFQfDR9YI9SFDyzCT3d` — python:S1110

Source: `venom_core/execution/skills/platform_skill.py:408`. Decision: **Accepted**.

The pair is semantically optional for this single string expression, so this is accepted formatting debt, not a false positive. Flattening preserves the AST, but the configured Ruff formatter restores the exact pair because of line length. Retain formatter consistency rather than add a temporary variable, a formatter suppression or an overlong line solely for this finding.

Validation: ruff format --check (8 files); parentheses-evidence.json (AST and formatter round-trip).

Revisit: Re-review if the message, indentation or formatter policy changes so that a single-line expression is retained.

## Verification and limits

- `pytest -q tests/test_system_llm_service.py tests/test_maf_runtime.py tests/test_llm_server_selection.py`: **92 PASS**.
- `node --import tsx --test --test-reporter=spec tests/api-client-retry.test.ts` (web-next): **6 PASS**.
- `node --import tsx --import ./tests/component-test-setup.ts --test --test-concurrency=1 --test-reporter=spec tests/multi-runtime-readiness.component.test.tsx` (web-next): **3 PASS**.
- `ruff format --check` on the eight S1110 files: **PASS**; AST/formatter checks confirm the two accepted pairs are restored by the formatter.
- Documentation-only repository change: hard gates skipped by policy; changed-lines coverage **N/A**. No runtime, configuration or dependency changes. The already recorded main `make pr-fast` remains 3981 PASS / 8 SKIP, not a new test run for this review.
- Tests use existing isolated transports and timers; no model, device, production network timeout or robot test was run. HTTPX phase-limit semantics are verified from the client configuration and documentation, not by pretending a mock measures real network deadlines.

## Sources

- [S9382 rule and dependent-loop exceptions](https://rules.sonarsource.com/typescript/RSPEC-9382/); the live rule text was read from SonarCloud `api/rules/show` for organization `mpieniak01`.
- [ESLint no-await-in-loop exceptions](https://eslint.org/docs/latest/rules/no-await-in-loop#when-not-to-use-it).
- [HTTPX phase timeouts](https://www.python-httpx.org/advanced/timeouts/).
- [Python implicit line joining](https://docs.python.org/3/reference/lexical_analysis.html#implicit-line-joining).

Polish summary: [SONAR_ISSUE_DISPOSITIONS.md](PL/SONAR_ISSUE_DISPOSITIONS.md).
