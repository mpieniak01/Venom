#!/usr/bin/env node

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const summaryPath = resolve(
  process.cwd(),
  process.env.E2E_TREND_SUMMARY_FILE ?? "test-results/e2e/flakiness-summary.json",
);

function fail(message) {
  console.error(`E2E quality gate FAILED: ${message}`);
  process.exit(1);
}

function readSummary(filePath) {
  if (!existsSync(filePath)) {
    fail(`missing summary file: ${filePath}`);
  }
  return JSON.parse(readFileSync(filePath, "utf8"));
}

function asNumber(value, fallback) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function main() {
  const summary = readSummary(summaryPath);
  const totals = summary?.totals ?? {};

  const minTests = asNumber(process.env.E2E_MIN_TESTS, 1);
  const maxFlakyRate = asNumber(process.env.E2E_MAX_FLAKY_RATE, 10);
  const allowFailures = process.env.E2E_ALLOW_FAILURES === "1";

  const total = asNumber(totals.total, 0);
  const failed = asNumber(totals.failed, 0);
  const timedOut = asNumber(totals.timedOut, 0);
  const interrupted = asNumber(totals.interrupted, 0);
  const flakyRate = asNumber(summary?.flakyRatePercent, 0);

  if (total < minTests) {
    fail(`total tests ${total} is below minimum ${minTests}`);
  }
  if (!allowFailures && (failed > 0 || timedOut > 0 || interrupted > 0)) {
    fail(`non-passing outcomes detected (failed=${failed}, timedOut=${timedOut}, interrupted=${interrupted})`);
  }
  if (flakyRate > maxFlakyRate) {
    fail(`flaky rate ${flakyRate}% exceeds max ${maxFlakyRate}%`);
  }

  console.log(
    `E2E quality gate PASSED: total=${total}, failed=${failed}, ` +
      `timedOut=${timedOut}, interrupted=${interrupted}, flakyRate=${flakyRate}%`,
  );
}

main();
