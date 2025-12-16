#!/usr/bin/env node
import { spawn } from "node:child_process";
import path from "node:path";

const rootDir = process.cwd();
const serverPath = path.join(rootDir, ".next", "standalone", "web-next", "server.js");

process.env.PORT = process.env.PORT || "3000";
process.env.HOSTNAME = process.env.HOSTNAME || "0.0.0.0";

const child = spawn("node", [serverPath], {
  cwd: rootDir,
  stdio: "inherit",
  env: process.env,
});

child.on("exit", (code) => {
  process.exit(code ?? 0);
});
child.on("error", (err) => {
  console.error("[start-server] Nie udało się uruchomić standalone server:", err);
  process.exit(1);
});
