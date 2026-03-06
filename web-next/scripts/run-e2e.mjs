#!/usr/bin/env node

import { spawn } from "node:child_process";

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
    console.log("⏭️  Testy E2E pominięte (brak gotowego środowiska).");
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
