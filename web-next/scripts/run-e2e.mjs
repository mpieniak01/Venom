#!/usr/bin/env node

import { spawn } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { summarizeProfiles } from "./e2e-profile-status.mjs";

const preflightStateFile = resolve(process.cwd(), process.env.E2E_PREFLIGHT_STATE_FILE || "test-results/e2e/preflight-state.json");
const skipTelemetryFile = resolve(process.cwd(), process.env.E2E_SKIP_TELEMETRY_FILE || "test-results/e2e/skip-reason-counts.json");
const summaryFile = resolve(process.cwd(), process.env.E2E_PROFILE_SUMMARY_FILE || "test-results/e2e/profile-summary.json");

function bumpSkipReasonCount(reasonCode) {
  mkdirSync(dirname(skipTelemetryFile), { recursive: true });
  let payload = { total_skips: 0, by_reason_code: {} };
  if (existsSync(skipTelemetryFile)) {
    try { payload = JSON.parse(readFileSync(skipTelemetryFile, "utf8")); } catch { /* start a fresh counter */ }
  }
  const code = String(reasonCode || "unknown");
  payload.total_skips = Number(payload.total_skips || 0) + 1;
  payload.by_reason_code ||= {};
  payload.by_reason_code[code] = Number(payload.by_reason_code[code] || 0) + 1;
  payload.updated_at = new Date().toISOString();
  writeFileSync(skipTelemetryFile, `${JSON.stringify(payload, null, 2)}\n`);
}

function writeSummary(profile, status, records, reason = "") {
  mkdirSync(dirname(summaryFile), { recursive: true });
  writeFileSync(summaryFile, `${JSON.stringify({ profile, status, reason, records, ...(profile === "simulated" ? { scope: "mocked_ui_without_physical_model" } : {}) }, null, 2)}\n`);
  console.log(`E2E ${profile}: ${status.toUpperCase()}${reason ? ` (${reason})` : ""}.`);
  if (status === "partial") console.log("Pełna kwalifikacja E2E nie została wykonana: co najmniej jeden profil pominięto.");
}

function run(command) {
  return new Promise((resolveRun) => {
    const child = spawn(command, { stdio: "inherit", shell: true, env: process.env });
    child.on("exit", (code) => resolveRun(code ?? 1));
    child.on("error", () => resolveRun(1));
  });
}

function resolveProfile() {
  const profile = String(process.env.E2E_PROFILE || "full").trim().toLowerCase();
  if (!["smoke", "functional", "simulated", "full"].includes(profile)) {
    throw new Error(`Nieobsługiwany profil E2E: ${profile}`);
  }
  return profile;
}

function shouldRunPreflight(profile) {
  const simulatedCi = process.env.GITHUB_ACTIONS === "true" && process.env.CI === "true" &&
    process.env.RUNNER_ENVIRONMENT === "github-hosted" && process.env.E2E_SIMULATED_SERVER === "1";
  if (!simulatedCi) return true;
  return process.env.E2E_FORCE_PREFLIGHT === "1" && profile === "full";
}

function readRecords(file) {
  if (!existsSync(file)) return [];
  return readFileSync(file, "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line));
}

async function main() {
  const profile = resolveProfile();
  const simulatedCi = process.env.GITHUB_ACTIONS === "true" && process.env.CI === "true" &&
    process.env.RUNNER_ENVIRONMENT === "github-hosted" && process.env.E2E_SIMULATED_SERVER === "1";
  if (profile === "simulated" && !simulatedCi) {
    writeSummary(profile, "failed", [], "simulated_profile_requires_github_hosted");
    process.exitCode = 1;
    return;
  }
  if (profile === "simulated") console.log("Zakres: symulowane API; fizyczne E2E z modelem nie jest wykonywane.");
  if (shouldRunPreflight(profile)) {
    const preflightCode = await run("npm run test:e2e:preflight");
    if (preflightCode === 2) {
      let reason = "unknown";
      try { reason = JSON.parse(readFileSync(preflightStateFile, "utf8")).reason_code || "unknown"; } catch { /* no state available */ }
      bumpSkipReasonCount(reason);
      writeSummary(profile, "skipped", [], reason);
      process.exitCode = 2;
      return;
    }
    if (preflightCode !== 0) {
      writeSummary(profile, "failed", [], "preflight_error");
      process.exitCode = preflightCode;
      return;
    }
  }

  const selected = profile === "full" ? ["smoke", "academy", "latency", "functional"] : profile === "simulated" ? ["smoke", "functional"] : [profile];
  const commands = { smoke: "test:e2e:smoke", academy: "test:e2e:smoke:academy", latency: "test:e2e:latency", functional: "test:e2e:functional" };
  const temp = mkdtempSync(join(tmpdir(), "venom-e2e-run-"));
  const resultsFile = join(temp, "results.jsonl");
  process.env.E2E_PROFILE_RESULT_FILE = resultsFile;
  try {
    let stageCode = 0;
    const durations = {};
    const originalEnv = { ...process.env };
    const simulatedOutputDir = resolve(process.cwd(), process.env.E2E_SIMULATED_REPORT_DIR || "test-results/e2e");
    if (profile === "simulated") {
      for (const name of selected) {
        for (const suffix of [`results-${name}.json`, `flakiness-summary-${name}.json`, `flakiness-history-${name}.jsonl`]) {
          rmSync(join(simulatedOutputDir, suffix), { force: true });
        }
      }
    }
    try {
      for (const name of selected) {
        if (profile === "simulated") {
          process.env.PLAYWRIGHT_JSON_OUTPUT_NAME = join(temp, `results-${name}.json`);
          process.env.PLAYWRIGHT_JSON_OUTPUT_FILE = process.env.PLAYWRIGHT_JSON_OUTPUT_NAME;
          process.env.E2E_TREND_SUMMARY_FILE = join(temp, `flakiness-summary-${name}.json`);
          process.env.E2E_TREND_HISTORY_FILE = join(temp, `flakiness-history-${name}.jsonl`);
          process.env.E2E_PROFILE = name;
          process.env.E2E_PLAYWRIGHT_OUTPUT_DIR = join(simulatedOutputDir, `playwright-${name}`);
          process.env.E2E_MIN_TESTS = name === "smoke" ? "5" : "8";
          process.env.E2E_MAX_FLAKY_RATE = name === "smoke" ? "15" : "10";
          delete process.env.E2E_ALLOW_FAILURES;
        }
        const start = performance.now();
        stageCode = await run(`npm run ${commands[name]}`);
        durations[name] = Number(((performance.now() - start) / 1000).toFixed(3));
        if (stageCode !== 0) break;
        if (profile === "simulated") {
          stageCode = await run("node scripts/e2e-trend-report.mjs");
          if (stageCode === 0) stageCode = await run("node scripts/e2e-quality-gate.mjs");
          if (stageCode !== 0) break;
        }
      }
    } finally {
      if (profile === "simulated") {
        // Playwright clears test-results on each invocation. Publish only once,
        // after both profiles, so neither profile removes the other's report.
        const outputDir = simulatedOutputDir;
        mkdirSync(outputDir, { recursive: true });
        for (const name of selected) {
          for (const suffix of [`results-${name}.json`, `flakiness-summary-${name}.json`, `flakiness-history-${name}.jsonl`]) {
            const source = join(temp, suffix);
            if (existsSync(source)) copyFileSync(source, join(outputDir, suffix));
          }
        }
        for (const key of ["PLAYWRIGHT_JSON_OUTPUT_NAME", "PLAYWRIGHT_JSON_OUTPUT_FILE", "E2E_TREND_SUMMARY_FILE", "E2E_TREND_HISTORY_FILE", "E2E_PROFILE", "E2E_PLAYWRIGHT_OUTPUT_DIR", "E2E_MIN_TESTS", "E2E_MAX_FLAKY_RATE", "E2E_ALLOW_FAILURES"]) {
          if (originalEnv[key] === undefined) delete process.env[key];
          else process.env[key] = originalEnv[key];
        }
      }
    }
    const records = readRecords(resultsFile).map((record) => ({ ...record, duration_seconds: durations[record.profile] }));
    const status = stageCode === 0 ? summarizeProfiles(selected, records) : "failed";
    writeSummary(profile, status, records, stageCode ? "profile_error" : "");
    process.exitCode = status === "passed" ? 0 : status === "failed" ? (stageCode || 1) : 2;
  } finally {
    delete process.env.E2E_PROFILE_RESULT_FILE;
    rmSync(temp, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error("E2E profile error:", error);
  writeSummary("unknown", "failed", [], "runner_error");
  process.exitCode = 1;
});
