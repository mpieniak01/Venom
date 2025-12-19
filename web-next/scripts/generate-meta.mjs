import { execSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.join(__dirname, "..");

function safeExec(cmd) {
  try {
    return execSync(cmd, { cwd: projectRoot, stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
  } catch {
    return "unknown";
  }
}

const packageJsonPath = path.join(projectRoot, "package.json");
const pkg = JSON.parse(readFileSync(packageJsonPath, "utf-8"));
const commit = safeExec("git rev-parse --short HEAD");
const timestamp = new Date().toISOString();
const meta = {
  version: pkg.version ?? "0.0.0",
  commit,
  timestamp,
};

const publicDir = path.join(projectRoot, "public");
mkdirSync(publicDir, { recursive: true });
const targetPath = path.join(publicDir, "meta.json");
writeFileSync(targetPath, JSON.stringify(meta, null, 2));

console.log(`[meta] Wrote ${targetPath} -> ${meta.version} (${meta.commit})`);
