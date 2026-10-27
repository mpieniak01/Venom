#!/usr/bin/env node

import { spawn } from "node:child_process";
import { appendFileSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { playwrightReportStatus } from "./e2e-profile-status.mjs";

const profiles = {
  smoke: ["tests/smoke.spec.ts", "tests/model-introspection-drift-smoke.spec.ts", "tests/theme-cascade.spec.ts", "--workers=1"],
  academy: ["tests/academy-smoke.spec.ts", "--workers=1"],
  latency: ["tests/perf/chat-latency.spec.ts", "--workers=1"],
  functional: ["tests/chat-mode-routing.spec.ts", "tests/streaming.spec.ts", "tests/chat-context-icons.spec.ts"],
  prod: [],
  perf: ["--config", "playwright.perf.config.ts"],
  "perf-backend": ["--config", "playwright.perf.config.ts"],
};
const profile = process.argv[2];
if (!Object.hasOwn(profiles, profile)) {
  console.error(`Nieznany profil E2E: ${profile || "(brak)"}`);
  process.exit(1);
}
const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const simulatedCi = process.env.GITHUB_ACTIONS === "true" && process.env.CI === "true" &&
  process.env.RUNNER_ENVIRONMENT === "github-hosted" && process.env.E2E_SIMULATED_SERVER === "1";
const needsModel = ["latency", "perf", "perf-backend", "prod"].includes(profile);
const aggregate = Boolean(process.env.E2E_PROFILE_RESULT_FILE);

function run(executable, args, env = process.env) {
  return new Promise((resolveRun) => {
    const child = spawn(executable, args, { cwd: webRoot, env, stdio: "inherit" });
    child.on("error", () => resolveRun(1));
    child.on("exit", (code) => resolveRun(code ?? 1));
  });
}

function recordResult(status, reason = "") {
  const record = { profile, status, reason };
  if (aggregate) {
    const file = resolve(webRoot, process.env.E2E_PROFILE_RESULT_FILE);
    mkdirSync(dirname(file), { recursive: true });
    appendFileSync(file, `${JSON.stringify(record)}\n`);
  } else {
    const file = resolve(webRoot, process.env.E2E_PROFILE_SUMMARY_FILE || "test-results/e2e/profile-summary.json");
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, `${JSON.stringify(record, null, 2)}\n`);
  }
  console.log(`E2E profile ${profile}: ${status.toUpperCase()}${reason ? ` (${reason})` : ""}.`);
}

function recordSkip(reason) {
  const telemetryFile = resolve(webRoot, process.env.E2E_SKIP_TELEMETRY_FILE || "test-results/e2e/skip-reason-counts.json");
  let telemetry = { total_skips: 0, by_reason_code: {} };
  if (existsSync(telemetryFile)) {
    try { telemetry = JSON.parse(readFileSync(telemetryFile, "utf8")); } catch { /* start a fresh counter */ }
  }
  telemetry.total_skips = Number(telemetry.total_skips || 0) + 1;
  telemetry.by_reason_code ||= {};
  telemetry.by_reason_code[reason] = Number(telemetry.by_reason_code[reason] || 0) + 1;
  mkdirSync(dirname(telemetryFile), { recursive: true });
  writeFileSync(telemetryFile, `${JSON.stringify(telemetry, null, 2)}\n`);
  recordResult("skipped", reason);
}

function skippedExit() {
  return aggregate ? 0 : 2;
}

// CI may start a disposable mocked UI for UI profiles. Every physical latency
// profile checks the actual Venom instance even on an isolated CI runner.
const isPhysicalProfile = ["latency", "perf", "perf-backend"].includes(profile);
if (!simulatedCi || isPhysicalProfile) {
  const preflightCode = await run(process.execPath, [resolve(webRoot, "scripts/check-e2e-env.mjs")], {
    ...process.env,
    E2E_REQUIRE_MODEL: needsModel ? "1" : "0",
  });
  if (preflightCode === 2) {
    const stateFile = resolve(webRoot, process.env.E2E_PREFLIGHT_STATE_FILE || "test-results/e2e/preflight-state.json");
    let reason = "unknown";
    try { reason = JSON.parse(readFileSync(stateFile, "utf8")).reason_code || "unknown"; } catch { /* no state available */ }
    recordSkip(reason);
    process.exit(skippedExit());
  }
  if (preflightCode !== 0) {
    recordResult("failed", "preflight_error");
    process.exit(preflightCode);
  }
}

// Full production-mode browser coverage includes unclassified specs. Locally
// it must never rebuild the live .next directory or start another server.
if (profile === "prod" && !simulatedCi) {
  recordSkip("prod_requires_isolated_ci");
  process.exit(skippedExit());
}
if (profile === "prod") {
  const buildCode = await run("npm", ["run", "build"]);
  if (buildCode !== 0) {
    recordResult("failed", "build_error");
    process.exit(buildCode);
  }
}

const extraArgs = process.argv.slice(3);
if (simulatedCi && process.env.E2E_PLAYWRIGHT_OUTPUT_DIR) {
  extraArgs.push(`--output=${process.env.E2E_PLAYWRIGHT_OUTPUT_DIR}`);
}
if (!simulatedCi && profile === "functional") {
  if (extraArgs.some((arg) => arg === "--workers" || arg.startsWith("--workers="))) {
    recordResult("failed", "invalid_workers");
    console.error("Lokalny profil functional ma jeden worker; nie ustawiaj --workers.");
    process.exit(1);
  }
  extraArgs.push("--workers=1");
}
const reporterIndex = extraArgs.findIndex((arg) => arg === "--reporter" || arg.startsWith("--reporter="));
if (reporterIndex >= 0) {
  const reporter = extraArgs[reporterIndex].startsWith("--reporter=")
    ? extraArgs[reporterIndex].slice("--reporter=".length)
    : extraArgs[reporterIndex + 1] || "";
  if (!reporter.split(",").includes("json")) {
    recordResult("failed", "json_reporter_required");
    console.error("Profil E2E wymaga reportera JSON do wykrywania pominiętych testów.");
    process.exit(1);
  }
} else {
  extraArgs.push("--reporter=json,line");
}

const temp = mkdtempSync(join(tmpdir(), "venom-e2e-profile-"));
const reportFile = join(temp, "playwright.json");
const globalFile = join(temp, "global-preflight.json");
let status = "failed";
let reason = "missing_report";
let exitCode = 1;
try {
  const cli = resolve(webRoot, "node_modules/@playwright/test/cli.js");
  const code = await run(process.execPath, [cli, "test", ...profiles[profile], ...extraArgs], {
    ...process.env,
    PLAYWRIGHT_REUSE_SERVER: "true",
    PLAYWRIGHT_MODE: profile === "prod" ? "prod" : "dev",
    PLAYWRIGHT_JSON_OUTPUT_NAME: reportFile,
    PLAYWRIGHT_JSON_OUTPUT_FILE: reportFile,
    E2E_GLOBAL_PREFLIGHT_FILE: globalFile,
  });
  if (existsSync(globalFile)) {
    const globalResult = JSON.parse(readFileSync(globalFile, "utf8"));
    if (globalResult.status === "skipped") {
      status = "skipped";
      reason = globalResult.reason_code || "unknown";
      exitCode = skippedExit();
    }
  } else if (code !== 0) {
    reason = "playwright_error";
    exitCode = code;
  } else if (existsSync(reportFile)) {
    const report = JSON.parse(readFileSync(reportFile, "utf8"));
    status = playwrightReportStatus(report);
    reason = status === "passed" ? "" : "playwright_outcomes";
    exitCode = status === "failed" ? 1 : status === "passed" ? 0 : skippedExit();
  }
  const requestedOutput = process.env.PLAYWRIGHT_JSON_OUTPUT_FILE || process.env.PLAYWRIGHT_JSON_OUTPUT_NAME;
  if (existsSync(reportFile) && requestedOutput) {
    const requestedReport = resolve(webRoot, requestedOutput);
    mkdirSync(dirname(requestedReport), { recursive: true });
    copyFileSync(reportFile, requestedReport);
  }
} catch (error) {
  console.error("E2E report error:", error);
} finally {
  rmSync(temp, { recursive: true, force: true });
}
if (status === "skipped") recordSkip(reason);
else recordResult(status, reason);
process.exit(exitCode);
