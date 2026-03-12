#!/usr/bin/env node

import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const reportPath = resolve(
  process.cwd(),
  process.env.PLAYWRIGHT_JSON_OUTPUT_NAME ?? "test-results/e2e/results.json",
);
const summaryPath = resolve(
  process.cwd(),
  process.env.E2E_TREND_SUMMARY_FILE ?? "test-results/e2e/flakiness-summary.json",
);
const historyPath = resolve(
  process.cwd(),
  process.env.E2E_TREND_HISTORY_FILE ?? "test-results/e2e/flakiness-history.jsonl",
);
const profile = String(process.env.E2E_PROFILE || "unknown");

function parseJson(filePath) {
  const raw = readFileSync(filePath, "utf8");
  return JSON.parse(raw);
}

function pushHistoryEntry(filePath, entry) {
  mkdirSync(dirname(filePath), { recursive: true });
  const line = `${JSON.stringify(entry)}\n`;
  appendFileSync(filePath, line, "utf8");
}

function countTestOutcome(test) {
  const results = Array.isArray(test?.results) ? test.results : [];
  const statuses = results.map((result) => String(result?.status || "unknown"));

  let finalStatus = statuses.at(-1) || String(test?.outcome || "unknown");
  if (finalStatus === "expected") finalStatus = "passed";
  if (finalStatus === "unexpected") finalStatus = "failed";

  const hadFailure = statuses.some((status) => ["failed", "timedOut", "interrupted"].includes(status));
  const passedEventually = finalStatus === "passed";
  const flaky = hadFailure && passedEventually;

  return {
    finalStatus,
    retries: Math.max(0, statuses.length - 1),
    flaky,
  };
}

function walkSuite(suite, outTests) {
  for (const spec of suite?.specs ?? []) {
    for (const test of spec?.tests ?? []) {
      outTests.push(test);
    }
  }
  for (const child of suite?.suites ?? []) {
    walkSuite(child, outTests);
  }
}

function buildSummary(report) {
  const tests = [];
  for (const suite of report?.suites ?? []) {
    walkSuite(suite, tests);
  }

  const stats = {
    total: tests.length,
    passed: 0,
    failed: 0,
    skipped: 0,
    timedOut: 0,
    interrupted: 0,
    flaky: 0,
    retriesTotal: 0,
  };

  for (const test of tests) {
    const outcome = countTestOutcome(test);
    stats.retriesTotal += outcome.retries;
    if (outcome.flaky) stats.flaky += 1;

    switch (outcome.finalStatus) {
      case "passed":
        stats.passed += 1;
        break;
      case "skipped":
        stats.skipped += 1;
        break;
      case "timedOut":
        stats.timedOut += 1;
        break;
      case "interrupted":
        stats.interrupted += 1;
        break;
      case "failed":
      default:
        stats.failed += 1;
        break;
    }
  }

  const flakyRate = stats.total > 0 ? Number(((stats.flaky / stats.total) * 100).toFixed(2)) : 0;
  return {
    timestamp: new Date().toISOString(),
    profile,
    reportPath,
    totals: stats,
    flakyRatePercent: flakyRate,
  };
}

function main() {
  if (!existsSync(reportPath)) {
    console.warn(`Brak raportu Playwright JSON: ${reportPath}`);
    process.exit(0);
  }

  const report = parseJson(reportPath);
  const summary = buildSummary(report);

  mkdirSync(dirname(summaryPath), { recursive: true });
  writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
  pushHistoryEntry(historyPath, summary);

  console.log(
    `E2E trend summary: profile=${summary.profile}, total=${summary.totals.total}, ` +
      `failed=${summary.totals.failed}, flaky=${summary.totals.flaky}, ` +
      `flakyRate=${summary.flakyRatePercent}%`,
  );
}

main();
