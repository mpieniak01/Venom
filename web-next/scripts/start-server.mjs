#!/usr/bin/env node
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { nextDistDir } from "./build-paths.mjs";

const distDir = nextDistDir();
const rootDir = process.cwd();
const serverCandidates = [
  path.join(rootDir, distDir, "standalone", path.basename(rootDir), "server.js"),
  path.join(rootDir, distDir, "standalone", "server.js"),
];
const serverPath = serverCandidates.find((candidate) => existsSync(candidate));
const nodeExecPath = process.execPath;

process.env.PORT = process.env.PORT || "3000";
process.env.HOSTNAME = process.env.HOSTNAME || "0.0.0.0";

if (!serverPath) {
  console.error(
    `[start-server] Nie znaleziono standalone server.js. Sprawdzone ścieżki: ${serverCandidates.join(", ")}`,
  );
  process.exit(1);
}

const child = spawn(nodeExecPath, [serverPath], {
  cwd: rootDir,
  stdio: "inherit",
  env: process.env,
});

let requestedStop = false;
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    requestedStop = true;
    child.kill(signal);
  });
}
child.on("exit", (code) => {
  process.exit(code ?? (requestedStop ? 0 : 1));
});
child.on("error", (err) => {
  console.error("[start-server] Nie udało się uruchomić standalone server:", err);
  process.exit(1);
});
