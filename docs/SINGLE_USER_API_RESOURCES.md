# API resource lifecycle in the single-user profile

This note records the A02/A08 boundaries. It does not claim a new measured RAM
saving or qualify a different installation profile.

## Telemetry and request responsiveness

Model usage telemetry has a five-second sample TTL. Concurrent cold readers share
one refresh. A cold reader waits at most two seconds, then receives 503 with
reason_code MODELS_USAGE_TIMEOUT while the owned collector can finish. Repeated
timeouts or a disconnected HTTP reader do not start another collector.

Expired readers receive the last good sample with additive telemetry metadata:
sample_age_seconds, stale, refreshing and refresh_failed. Refresh failures do not
replace a good sample with zero. The owner identity prevents one ModelManager from
receiving another instance's cached data. Explicit invalidation prevents an older
refresh from republishing its sample.

Host sampling and local filesystem discovery run outside the request event loop.
Existing GPU collection already uses a worker thread and retains its subprocess
timeout. Python cannot forcibly interrupt a filesystem syscall in a worker thread;
a timeout bounds the HTTP wait, not the lifetime of such an OS operation. The
single-flight reference remains until completion rather than starting more scans.

This cache belongs to UI telemetry. Storage quota and runtime admission checks
continue to read current resource state through their existing independent paths.

## Owners and first use

The existing model_resources registry stores weak owner references and tracks
model work. Its release barrier drains active work before releasing resources.
A registry entry is not a second set of weights.

EmbeddingService already loads its model/client lazily and bounds its embedding
LRU to 1000 entries. A per-owner reentrant lock now serializes first-use loading:
concurrent requests cannot allocate duplicate models for that owner. Failed
initialization leaves the lock reusable. Sharing across different owners remains
a separate decision because mutable state and configuration must stay isolated.

Resource release clears the model and embedding cache and closes an existing
remote embedding client. A failed close is reported as unverified and retains the
client reference for a retry. The frequently used audio models retain their
existing asynchronous warmup and quality.

ONNX best-effort cleanup checks only entrypoints already present in sys.modules.
It must not import API routes or initialize unused dependencies merely to release
a runtime that was never used.

## Evidence and limits

Regression tests use fake model/client factories, synchronized concurrent calls,
slow collectors and fake transports. No provider request, CUDA initialization or
real model load is needed to verify these contracts.

The earlier Full installation API PSS of approximately 2.35 GiB does not attribute
memory to a particular library or owner. Per-function live PSS/VRAM and first-use
measurements belong to the integrated A09 acceptance. This change does not add a
worker process, replace the venv, remove audio readiness, or delete stored history
to produce an artificially lower idle result.
