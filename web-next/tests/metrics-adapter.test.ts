import test from "node:test";
import assert from "node:assert/strict";

import { normalizeMetrics, normalizeMetricsRequired } from "@/lib/metrics-adapter";

test("normalizeMetrics returns null for null payload", () => {
  assert.equal(normalizeMetrics(null), null);
});

test("normalizeMetrics normalizes invalid numeric values", () => {
  const normalized = normalizeMetrics({
    tasks: { created: Number.NaN, success_rate: 94.2 },
    routing: { llm_only: Infinity, tool_required: 2, learning_logged: 1 },
    feedback: { up: 10, down: Number.NaN },
    policy: { blocked_count: 0, block_rate: Number.NaN },
    network: { total_bytes: Number.NaN },
    uptime_seconds: Number.NaN,
  });

  assert.ok(normalized);
  assert.equal(normalized?.tasks?.created, undefined);
  assert.equal(normalized?.tasks?.success_rate, 94.2);
  assert.equal(normalized?.routing?.llm_only, undefined);
  assert.equal(normalized?.routing?.tool_required, 2);
  assert.equal(normalized?.feedback?.down, undefined);
  assert.equal(normalized?.policy?.blocked_count, 0);
  assert.equal(normalized?.network?.total_bytes, undefined);
  assert.equal(normalized?.uptime_seconds, undefined);
});

test("normalizeMetricsRequired always returns metrics payload", () => {
  const payload = {
    tasks: { created: 1, success_rate: 100 },
  };
  const normalized = normalizeMetricsRequired(payload);
  assert.equal(normalized.tasks?.created, 1);
});
