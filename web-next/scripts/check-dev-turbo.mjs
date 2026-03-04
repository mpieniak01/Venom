#!/usr/bin/env node

/**
 * Smoke check for Next dev:turbo mode.
 * Starts `npm run dev:turbo` on a dedicated port and verifies key routes.
 */

import { spawn } from "node:child_process";
import { rm } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const HOST = process.env.TURBO_SMOKE_HOST ?? "127.0.0.1";
const PORT = process.env.TURBO_SMOKE_PORT ?? "3010";
const BASE_URL = `http://${HOST}:${PORT}`;
const START_TIMEOUT_MS = Number.parseInt(
  process.env.TURBO_SMOKE_START_TIMEOUT_MS ?? "120000",
  10,
);
const REQUEST_TIMEOUT_MS = Number.parseInt(
  process.env.TURBO_SMOKE_REQUEST_TIMEOUT_MS ?? "5000",
  10,
);
const CLEAN_NEXT = process.env.TURBO_SMOKE_CLEAN_NEXT === "1";

const REQUIRED_ROUTES = ["/", "/academy", "/benchmark"];
const RECENT_LOG_LINES = 120;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithTimeout(url, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    return { ok: res.ok, status: res.status };
  } finally {
    clearTimeout(timer);
  }
}

async function waitForServerReady(baseUrl, timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const res = await fetchWithTimeout(baseUrl, REQUEST_TIMEOUT_MS);
      if (res.status < 500) {
        return true;
      }
    } catch {
      // retry
    }
    await sleep(1000);
  }
  return false;
}

function buildRecentLogs(buffer) {
  return buffer.slice(-RECENT_LOG_LINES).join("\n");
}

async function terminateProcess(proc) {
  if (!proc || proc.exitCode !== null || proc.killed) {
    return;
  }
  const pid = proc.pid ?? null;
  if (pid !== null && pid > 0) {
    try {
      process.kill(-pid, "SIGTERM");
    } catch {
      proc.kill("SIGTERM");
    }
  } else {
    proc.kill("SIGTERM");
  }
  await sleep(1500);
  if (proc.exitCode === null) {
    if (pid !== null && pid > 0) {
      try {
        process.kill(-pid, "SIGKILL");
      } catch {
        proc.kill("SIGKILL");
      }
    } else {
      proc.kill("SIGKILL");
    }
  }
}

async function main() {
  const webRoot = process.cwd();
  const nextDir = path.join(webRoot, ".next");
  const env = {
    ...process.env,
    NEXT_TELEMETRY_DISABLED: "1",
    NEXT_DEBUG: process.env.NEXT_DEBUG ?? "true",
  };
  const outputLines = [];

  if (CLEAN_NEXT) {
    await rm(nextDir, { recursive: true, force: true });
    console.log(`🧹 Removed ${nextDir}`);
  }

  console.log(
    `▶ Starting dev:turbo smoke on ${BASE_URL} (timeout=${START_TIMEOUT_MS}ms)`,
  );
  const proc = spawn(
    "npm",
    ["run", "dev:turbo", "--", "--hostname", HOST, "--port", PORT],
    {
      cwd: webRoot,
      env,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  proc.stdout.on("data", (chunk) => {
    const text = String(chunk);
    for (const line of text.split("\n")) {
      if (line.trim()) {
        outputLines.push(`[stdout] ${line}`);
      }
    }
  });
  proc.stderr.on("data", (chunk) => {
    const text = String(chunk);
    for (const line of text.split("\n")) {
      if (line.trim()) {
        outputLines.push(`[stderr] ${line}`);
      }
    }
  });

  try {
    const ready = await waitForServerReady(BASE_URL, START_TIMEOUT_MS);
    if (!ready) {
      throw new Error(
        "dev:turbo did not become reachable before timeout. Recent logs:\n" +
          buildRecentLogs(outputLines),
      );
    }

    for (const route of REQUIRED_ROUTES) {
      const url = `${BASE_URL}${route}`;
      const res = await fetchWithTimeout(url, REQUEST_TIMEOUT_MS);
      if (res.status >= 500) {
        throw new Error(
          `Route check failed for ${route}: status=${res.status}\n` +
            buildRecentLogs(outputLines),
        );
      }
      console.log(`✅ ${route} status=${res.status}`);
    }

    console.log("✅ dev:turbo smoke passed");
  } finally {
    await terminateProcess(proc);
  }
}

main().catch((err) => {
  console.error("❌ dev:turbo smoke failed");
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
