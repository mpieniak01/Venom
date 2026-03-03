/**
 * Testy pomocników hooka use-coding-benchmark oraz adapterów danych wykresów.
 * Weryfikuje logikę mapowania statusu i budowania logów postępu.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolvePollStatus, buildProgressLog } from "../hooks/use-coding-benchmark";
import {
  computePassRates,
  computeTimings,
} from "../components/benchmark/benchmark-coding-charts";

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

  it("returns progress object when total_jobs > 0", () => {
    const result = buildProgressLog({ completed: 3, total_jobs: 10 });
    assert.ok(result !== null, "Expected non-null result");
    assert.strictEqual(result?.completed, 3);
    assert.strictEqual(result?.total, 10);
  });

  it("returns correct object for fully completed run", () => {
    const result = buildProgressLog({ completed: 5, total_jobs: 5 });
    assert.ok(result !== null);
    assert.strictEqual(result?.completed, 5);
    assert.strictEqual(result?.total, 5);
  });
});

// ─── Chart data adapters ─────────────────────────────────────────────────────

const makeJob = (
  overrides: Partial<{
    id: string;
    model: string;
    mode: string;
    task: string;
    role: string;
    status: string;
    created_at: string;
    passed: boolean | null;
    warmup_seconds: number | null;
    coding_seconds: number | null;
    request_wall_seconds: number | null;
  }>,
) => ({
  id: "j1",
  model: "llama3",
  mode: "ollama",
  task: "python_complex",
  role: "primary",
  status: "completed",
  created_at: new Date().toISOString(),
  passed: true,
  warmup_seconds: 1.0,
  coding_seconds: 2.0,
  request_wall_seconds: 3.0,
  total_seconds: 6.0,
  ...overrides,
});

describe("computePassRates", () => {
  it("returns empty array for empty jobs", () => {
    const result = computePassRates([]);
    assert.deepStrictEqual(result, []);
  });

  it("computes 100% pass rate for all-passed jobs", () => {
    const jobs = [makeJob({ model: "m1", passed: true }), makeJob({ model: "m1", passed: true })];
    const rates = computePassRates(jobs);
    assert.strictEqual(rates.length, 1);
    assert.strictEqual(rates[0].model, "m1");
    assert.strictEqual(rates[0].passRate, 100);
    assert.strictEqual(rates[0].passed, 2);
    assert.strictEqual(rates[0].total, 2);
  });

  it("computes 0% pass rate for all-failed jobs", () => {
    const jobs = [makeJob({ model: "m2", passed: false })];
    const rates = computePassRates(jobs);
    assert.strictEqual(rates[0].passRate, 0);
  });

  it("computes 50% pass rate for mixed results", () => {
    const jobs = [
      makeJob({ id: "j1", model: "m3", passed: true }),
      makeJob({ id: "j2", model: "m3", passed: false }),
    ];
    const rates = computePassRates(jobs);
    assert.strictEqual(rates[0].passRate, 50);
  });

  it("groups by model correctly", () => {
    const jobs = [
      makeJob({ id: "a", model: "alpha", passed: true }),
      makeJob({ id: "b", model: "beta", passed: false }),
    ];
    const rates = computePassRates(jobs);
    assert.strictEqual(rates.length, 2);
    const alpha = rates.find((r) => r.model === "alpha");
    const beta = rates.find((r) => r.model === "beta");
    assert.ok(alpha && alpha.passRate === 100);
    assert.ok(beta && beta.passRate === 0);
  });
});

describe("computeTimings", () => {
  it("returns empty array for empty jobs", () => {
    assert.deepStrictEqual(computeTimings([]), []);
  });

  it("averages timing fields per model", () => {
    const jobs = [
      makeJob({ id: "j1", model: "m1", warmup_seconds: 2.0, coding_seconds: 4.0, request_wall_seconds: 6.0 }),
      makeJob({ id: "j2", model: "m1", warmup_seconds: 4.0, coding_seconds: 8.0, request_wall_seconds: 12.0 }),
    ];
    const timings = computeTimings(jobs);
    assert.strictEqual(timings.length, 1);
    assert.strictEqual(timings[0].warmupSeconds, 3.0);
    assert.strictEqual(timings[0].codingSeconds, 6.0);
    assert.strictEqual(timings[0].requestSeconds, 9.0);
  });

  it("skips null timing fields", () => {
    const jobs = [
      makeJob({ id: "j1", model: "m1", warmup_seconds: null, coding_seconds: 5.0, request_wall_seconds: null }),
    ];
    const timings = computeTimings(jobs);
    assert.strictEqual(timings[0].warmupSeconds, 0);
    assert.strictEqual(timings[0].codingSeconds, 5.0);
    assert.strictEqual(timings[0].requestSeconds, 0);
  });
});
