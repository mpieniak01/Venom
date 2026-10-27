#!/usr/bin/env node

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
  writeFileSync(summaryFile, `${JSON.stringify({ profile, status, reason, records }, null, 2)}\n`);
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
  if (!["smoke", "functional", "full"].includes(profile)) {
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

  const selected = profile === "full" ? ["smoke", "academy", "latency", "functional"] : [profile];
  const commands = { smoke: "test:e2e:smoke", academy: "test:e2e:smoke:academy", latency: "test:e2e:latency", functional: "test:e2e:functional" };
  const temp = mkdtempSync(join(tmpdir(), "venom-e2e-run-"));
  const resultsFile = join(temp, "results.jsonl");
  process.env.E2E_PROFILE_RESULT_FILE = resultsFile;
  try {
    let stageCode = 0;
    for (const name of selected) {
      stageCode = await run(`npm run ${commands[name]}`);
      if (stageCode !== 0) break;
    }
    const records = readRecords(resultsFile);
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
