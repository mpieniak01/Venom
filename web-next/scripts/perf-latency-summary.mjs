#!/usr/bin/env node

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const reportPath = resolve(
  process.cwd(),
  process.env.PLAYWRIGHT_JSON_OUTPUT_NAME ?? "test-results/e2e/results-perf.json",
);
const summaryPath = resolve(
  process.cwd(),
  process.env.PERF_SUMMARY_FILE ?? "test-results/e2e/perf-summary.json",
);
const maxLatencyMs = Number(process.env.PERF_MAX_LATENCY_MS ?? 0);

function toLatencyMs(text) {
  const match = String(text || "").match(/(\d+(?:\.\d+)?)ms/i);
  if (!match) return null;
  const value = Number(match[1]);
  return Number.isFinite(value) ? value : null;
}

function walkSuite(suite, tests) {
  for (const spec of suite?.specs ?? []) {
    for (const test of spec?.tests ?? []) {
      tests.push(test);
    }
  }
  for (const child of suite?.suites ?? []) {
    walkSuite(child, tests);
  }
}

function gatherLatencies(report) {
  const tests = [];
  for (const suite of report?.suites ?? []) {
    walkSuite(suite, tests);
  }

  const latencies = [];
  for (const test of tests) {
    const annotations = Array.isArray(test?.annotations) ? test.annotations : [];
    for (const annotation of annotations) {
      if (annotation?.type !== "latency") continue;
      const parsed = toLatencyMs(annotation?.description);
      if (parsed !== null) {
        latencies.push(parsed);
      }
    }
  }
  return latencies;
}

function fail(message) {
  console.error(`Perf summary FAILED: ${message}`);
  process.exit(1);
}

function main() {
  if (!existsSync(reportPath)) {
    fail(`missing Playwright JSON report: ${reportPath}`);
  }

  const report = JSON.parse(readFileSync(reportPath, "utf8"));
  const latencies = gatherLatencies(report);
  if (latencies.length === 0) {
    fail("no latency annotations found in report");
  }

  const max = Math.max(...latencies);
  const min = Math.min(...latencies);
  const avg = latencies.reduce((acc, value) => acc + value, 0) / latencies.length;

  const summary = {
    timestamp: new Date().toISOString(),
    reportPath,
    samples: latencies.length,
    minLatencyMs: Number(min.toFixed(2)),
    avgLatencyMs: Number(avg.toFixed(2)),
    maxLatencyMs: Number(max.toFixed(2)),
    thresholdMs: maxLatencyMs > 0 ? maxLatencyMs : null,
  };

  mkdirSync(dirname(summaryPath), { recursive: true });
  writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");

  if (maxLatencyMs > 0 && max > maxLatencyMs) {
    fail(`max latency ${max.toFixed(2)}ms exceeds threshold ${maxLatencyMs}ms`);
  }

  console.log(
    `Perf summary: samples=${summary.samples}, min=${summary.minLatencyMs}ms, ` +
      `avg=${summary.avgLatencyMs}ms, max=${summary.maxLatencyMs}ms`,
  );
}

main();
