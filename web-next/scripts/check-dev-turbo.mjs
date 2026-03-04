#!/usr/bin/env node

/**
 * Smoke check for Next dev:turbo mode.
 * Starts `npm run dev:turbo` on a dedicated port and verifies key routes.
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
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
const MAX_LOG_BUFFER_LINES = RECENT_LOG_LINES * 4;
const FAILURE_HINTS = [
  {
    pattern: /\.next[\\/]+dev[\\/]+lock/i,
    hint:
      "Detected `.next/dev/lock` conflict. Stop other Next dev instances and rerun. Example: `pkill -f \"next dev\"`.",
  },
  {
    pattern: /module not found|can't resolve/i,
    hint:
      "Detected module resolution error. Verify import paths and `npm --prefix web-next ci` state.",
  },
  {
    pattern: /unsupported|not implemented|webpack/i,
    hint:
      "Detected potential Webpack-only behavior. Check `next.config.ts` and webpack-specific imports/loaders.",
  },
];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function appendOutputLine(buffer, line) {
  if (!line.trim()) {
    return;
  }
  buffer.push(line);
  if (buffer.length > MAX_LOG_BUFFER_LINES) {
    buffer.splice(0, buffer.length - MAX_LOG_BUFFER_LINES);
  }
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

function detectFailureHints(buffer) {
  const recent = buildRecentLogs(buffer);
  return FAILURE_HINTS.filter(({ pattern }) => pattern.test(recent)).map(
    ({ hint }) => hint,
  );
}

function buildFailureReport(reason, buffer) {
  const hints = detectFailureHints(buffer);
  const hintsBlock =
    hints.length > 0 ? `\n\nHints:\n- ${hints.join("\n- ")}` : "";
  return `${reason}\n\nRecent logs:\n${buildRecentLogs(buffer)}${hintsBlock}`;
}

async function waitForServerReady(baseUrl, timeoutMs, proc) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (proc.exitCode !== null) {
      return {
        ready: false,
        reason: `dev:turbo exited early with code=${proc.exitCode}`,
      };
    }
    try {
      const res = await fetchWithTimeout(baseUrl, REQUEST_TIMEOUT_MS);
      if (res.status < 500) {
        return { ready: true, reason: null };
      }
    } catch {
      // retry
    }
    await sleep(1000);
  }
  return {
    ready: false,
    reason: `dev:turbo not reachable within ${timeoutMs}ms`,
  };
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

function installSignalHandlers(proc) {
  const stopAndExit = (code) => {
    terminateProcess(proc)
      .catch(() => null)
      .finally(() => {
        process.exit(code);
      });
  };
  process.once("SIGINT", () => stopAndExit(130));
  process.once("SIGTERM", () => stopAndExit(143));
}

async function main() {
  const webRoot = process.cwd();
  const nextDir = path.join(webRoot, ".next");
  const lockFile = path.join(nextDir, "dev", "lock");
  const env = {
    ...process.env,
    NEXT_TELEMETRY_DISABLED: "1",
    NEXT_DEBUG: process.env.NEXT_DEBUG ?? "true",
  };
  const outputLines = [];
  let spawnFailureReason = null;

  if (CLEAN_NEXT) {
    if (existsSync(lockFile)) {
      throw new Error(
        `Refusing to remove ${nextDir}: lock file exists (${lockFile}). Stop active Next dev process first.`,
      );
    }
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
  installSignalHandlers(proc);
  proc.on("error", (err) => {
    spawnFailureReason =
      err instanceof Error
        ? `Failed to spawn npm dev:turbo: ${err.message}`
        : "Failed to spawn npm dev:turbo";
    appendOutputLine(outputLines, `[spawn-error] ${spawnFailureReason}`);
  });

  proc.stdout.on("data", (chunk) => {
    const text = String(chunk);
    for (const line of text.split("\n")) {
      appendOutputLine(outputLines, `[stdout] ${line}`);
    }
  });
  proc.stderr.on("data", (chunk) => {
    const text = String(chunk);
    for (const line of text.split("\n")) {
      appendOutputLine(outputLines, `[stderr] ${line}`);
    }
  });

  try {
    if (spawnFailureReason) {
      throw new Error(buildFailureReport(spawnFailureReason, outputLines));
    }
    const readyResult = await waitForServerReady(BASE_URL, START_TIMEOUT_MS, proc);
    if (spawnFailureReason) {
      throw new Error(buildFailureReport(spawnFailureReason, outputLines));
    }
    if (!readyResult.ready) {
      throw new Error(
        buildFailureReport(
          readyResult.reason ?? "dev:turbo startup failed",
          outputLines,
        ),
      );
    }

    for (const route of REQUIRED_ROUTES) {
      const url = `${BASE_URL}${route}`;
      const res = await fetchWithTimeout(url, REQUEST_TIMEOUT_MS);
      if (res.status >= 400) {
        throw new Error(
          buildFailureReport(
            `Route check failed for ${route}: status=${res.status}`,
            outputLines,
          ),
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
