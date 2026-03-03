/**
 * Testy pomocników hooka use-coding-benchmark.
 * Weryfikuje logikę mapowania statusu i budowania logów postępu.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolvePollStatus, buildProgressLog } from "../hooks/use-coding-benchmark";

describe("resolvePollStatus", () => {
  it("returns completed for completed status", () => {
    assert.strictEqual(resolvePollStatus("completed"), "completed");
  });

  it("returns failed for failed status", () => {
    assert.strictEqual(resolvePollStatus("failed"), "failed");
  });

  it("returns running for running status", () => {
    assert.strictEqual(resolvePollStatus("running"), "running");
  });

  it("returns null for pending status", () => {
    assert.strictEqual(resolvePollStatus("pending"), null);
  });

  it("returns null for unknown status", () => {
    assert.strictEqual(resolvePollStatus("unknown_value"), null);
  });
});

describe("buildProgressLog", () => {
  it("returns null when summary is null", () => {
    assert.strictEqual(buildProgressLog(null), null);
  });

  it("returns null when summary is undefined", () => {
    assert.strictEqual(buildProgressLog(undefined), null);
  });

  it("returns null when total_jobs is zero", () => {
    assert.strictEqual(buildProgressLog({ completed: 0, total_jobs: 0 }), null);
  });

  it("returns progress string when total_jobs > 0", () => {
    const result = buildProgressLog({ completed: 3, total_jobs: 10 });
    assert.ok(result !== null, "Expected non-null result");
    assert.ok(result.includes("3"), "Should contain completed count");
    assert.ok(result.includes("10"), "Should contain total count");
  });

  it("returns correct string for fully completed run", () => {
    const result = buildProgressLog({ completed: 5, total_jobs: 5 });
    assert.ok(result !== null);
    assert.ok(result.includes("5/5"));
  });
});
