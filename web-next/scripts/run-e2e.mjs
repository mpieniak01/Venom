#!/usr/bin/env node

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const preflightStateFile = resolve(
  process.cwd(),
  // 197B policy: preflight owns environment diagnosis and reason_code classification.
  process.env.E2E_PREFLIGHT_STATE_FILE ?? "test-results/e2e/preflight-state.json",
);
const skipTelemetryFile = resolve(
  process.cwd(),
  process.env.E2E_SKIP_TELEMETRY_FILE ?? "test-results/e2e/skip-reason-counts.json",
);

function bumpSkipReasonCount(reasonCode) {
  mkdirSync(dirname(skipTelemetryFile), { recursive: true });
  let payload = { total_skips: 0, by_reason_code: {} };
  if (existsSync(skipTelemetryFile)) {
    try {
      payload = JSON.parse(readFileSync(skipTelemetryFile, "utf8"));
    } catch {
      payload = { total_skips: 0, by_reason_code: {} };
    }
  }
  const code = String(reasonCode || "unknown");
  payload.total_skips = Number(payload.total_skips || 0) + 1;
  payload.by_reason_code = payload.by_reason_code || {};
  payload.by_reason_code[code] = Number(payload.by_reason_code[code] || 0) + 1;
  payload.updated_at = new Date().toISOString();
  writeFileSync(`${skipTelemetryFile}`, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

function run(command) {
  return new Promise((resolve) => {
    const child = spawn(command, {
      stdio: "inherit",
      shell: true,
      env: process.env,
    });
    child.on("exit", (code) => resolve(code ?? 1));
    child.on("error", () => resolve(1));
  });
}

async function main() {
  const preflightCode = await run("npm run test:e2e:preflight");
  if (preflightCode === 2) {
    // exit=2 means "skip due to environment preconditions", not test failure.
    let reasonCode = "unknown";
    if (existsSync(preflightStateFile)) {
      try {
        const payload = JSON.parse(readFileSync(preflightStateFile, "utf8"));
        reasonCode = payload?.reason_code || "unknown";
        const message = payload?.message || "brak dodatkowych informacji";
        console.log(
          `⏭️  Testy E2E pominięte (reason_code=${reasonCode}, state=${payload?.state || "n/a"}).`,
        );
        console.log(`   ${message}`);
      } catch {
        console.log("⏭️  Testy E2E pominięte (brak gotowego środowiska).");
      }
    } else {
      console.log("⏭️  Testy E2E pominięte (brak gotowego środowiska).");
    }
    bumpSkipReasonCount(reasonCode);
    process.exit(0);
  }
  if (preflightCode !== 0) {
    process.exit(preflightCode);
  }

  const latencyCode = await run("npm run test:e2e:latency");
  if (latencyCode !== 0) {
    process.exit(latencyCode);
  }

  const functionalCode = await run("npm run test:e2e:functional");
  process.exit(functionalCode);
}

main().catch(() => process.exit(1));
