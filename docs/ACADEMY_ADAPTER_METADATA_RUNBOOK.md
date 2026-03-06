# Academy Adapter Metadata Repair Runbook

## Purpose

Provide an operational path for historical adapters that fail deployment due to missing or inconsistent `base_model` metadata.

## Symptoms

Typical `reason_code` values during activation/deploy:

1. `ADAPTER_BASE_MODEL_UNKNOWN`
2. `ADAPTER_METADATA_INCONSISTENT`
3. `ADAPTER_BASE_MODEL_MISMATCH`

## Preflight Audit

Run preflight audit before deployment:

```bash
curl -s "http://localhost:8000/api/v1/academy/adapters/audit?runtime_id=ollama&model_id=<runtime_model>"
```

Expected categories:

1. `compatible`
2. `blocked_unknown_base`
3. `blocked_mismatch`

## Minimal Metadata Contract

To unblock deployment, each adapter should expose one consistent base model across artifacts:

1. `<adapter_dir>/metadata.json` with `base_model`
2. Optional but recommended: `<adapter_dir>/adapter/adapter_config.json` with `base_model_name_or_path`
3. Optional: `<adapter_dir>/runtime_vllm/venom_runtime_vllm.json` with `base_model`

## Manual Repair Procedure

1. Identify adapter from audit output (`adapter_id`, `sources`, `reason_code`).
2. Determine true training base model from training logs or model registry.
3. Update `metadata.json` so `base_model` matches the real training base.
4. If `adapter_config.json` exists, align `base_model_name_or_path` to the same canonical base.
5. Remove conflicting stale manifests if they cannot be aligned.
6. Re-run `/api/v1/academy/adapters/audit`.
7. Deploy only when category becomes `compatible`.

## Validation Checklist

1. Audit category is `compatible`.
2. `reason_code` is empty.
3. Runtime selected model canonical ID matches adapter canonical base model.
4. Activation call returns success.

## Notes

1. The system intentionally blocks uncertain deployments (strict metadata confidence) to avoid silent wrong runtime overlays.
2. Default config base model alone is not considered trusted evidence for deployment safety.
