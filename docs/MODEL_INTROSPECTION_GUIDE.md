# Model Introspection - operational guide

This document describes the `Inspector / Model Introspection` screen in `web-next` and how to read the signals introduced by the 223D/223E implementation work.

Flow Inspector still lives at `/inspector`. Model introspection is a separate screen at `/inspector/model-introspection`.

---

## 1. Purpose

- show the model answer, analysis flow, and mechanistic signals in one place,
- separate answer quality from internals quality,
- make it obvious when introspection is complete vs. when it is falling back,
- keep the UI stable even when probes are unavailable or partial.

## 2. Current state vs target state

| State | What you see | How to interpret it |
|---|---|---|
| transitional / degraded | `internals fallback`, `attention_unavailable`, `saliency_unavailable`, `probe_failed` | The UI is healthy, but probes did not deliver full internals data for this run |
| target / ready | separate `answer verdict` and `internals verdict`, data for `attention`, `saliency`, `logit lens` | Analysis is complete and does not depend on fallback paths |

## 3. Data contract

The view is driven by `analysis_capabilities`.

### 3.1 Runtime / probe readiness

- `probe_profile`
- `probe_enabled`
- `probe_healthy`
- `runtime_supported`
- `endpoint_configured`
- `model_whitelisted`
- `limits.*`:
  - `timeout_seconds`
  - `max_attempts`
  - `max_top_k`
  - `max_layer_count`
  - `max_head_count`
  - `max_prompt_tokens`

### 3.2 Mechanism state

Each mechanism returns an explicit status and reason:

- `attention`
- `saliency`
- `logit_lens`

In practice the UI distinguishes:

- `available`
- `unavailable`
- `probe_failed`
- `probe_unavailable`

## 4. How to read the screen

### 4.1 Answer verdict

This is the answer-quality and grounding signal:

- whether the response is coherent,
- whether it is grounded,
- whether evidence coverage is sufficient.

### 4.2 Internals verdict

This is the separate signal for introspection mechanisms:

- whether runtime and endpoint are ready,
- whether the model is whitelisted,
- whether probes returned data,
- whether the issue is just fallback or a real absence of internals.

### 4.3 Timeline reading

The timeline now separates two paths:

- `answer_path`
- `internals_path`

This helps identify whether a delay is caused by the answer itself or by additional probes.

## 5. When the state is transitional

The state is transitional if:

- runtime reports `supported`, `configured`, `whitelisted`, `enabled`,
- but internals still show `fallback` or `unavailable`,
- or `logit lens` ends with `probe_failed`.

This does not mean the UI failed. It means the control plane is working, but probes for this run did not produce full data.

## 6. Readiness criteria

The phase is only ready when all of the following are true:

- `probe success rate >= 90%` over a 20-run window,
- `first chunk p95 <= 2500 ms`,
- 3 consecutive validation windows pass,
- `answer verdict` and `internals verdict` are clearly separated,
- `analysis_capabilities` shows full runtime/probe readiness or an explicit reason for unavailability,
- pre-commit, lint, typecheck, and component tests are green.

## 7. Common scenarios

### 7.1 `probe budget unknown`

The UI does not yet have a full probe budget snapshot. This is informational, not necessarily a failure.

### 7.2 `attention_unavailable` / `saliency_unavailable`

The mechanism is in fallback state or did not receive data for this run. Check probe readiness and runtime logs.

### 7.3 `probe_failed`

Logit lens or another probe did not complete successfully. If this repeats, it is no longer a one-off transient.

### 7.4 `internals fallback` with a good answer verdict

This is an expected transitional state. The answer may be correct even while internals are still incomplete.

## 8. Related documents

- [223DA implementation plan](../docs_dev/_to_do/223DA_pr_plan_realizacji_attention_saliency_dev.md)
- [223E gap analysis](../docs_dev/_to_do/223E_pr_analiza_gap_live_analysis_dev.md)
- [225 target direction](../docs_dev/_to_do/225_pr_docelowy_kierunek_introspection_dev.md)
- [README](../README.md)
- [Frontend Next.js](./FRONTEND_NEXT_GUIDE.md)
- [Dashboard Guide](./DASHBOARD_GUIDE.md)
- [Runtime drift runbook (EN)](./runbooks/model-introspection-runtime-drift.md)
