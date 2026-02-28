import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.join(__dirname, "..");

function safeExecFile(file, args = []) {
  try {
    return execFileSync(file, args, {
      cwd: projectRoot,
      stdio: ["ignore", "pipe", "ignore"],
      encoding: "utf8",
    }).trim();
  } catch {
    return "unknown";
  }
}

const packageJsonPath = path.join(projectRoot, "package.json");
const pkg = JSON.parse(readFileSync(packageJsonPath, "utf-8"));
const commit = safeExecFile("git", ["rev-parse", "--short", "HEAD"]);
const timestamp = new Date().toISOString();
const environmentRoleRaw = (process.env.ENVIRONMENT_ROLE || "dev").trim().toLowerCase();
const environmentRole =
  ["preprod", "pre-prod", "pre_prod", "staging", "stage"].includes(environmentRoleRaw)
    ? "preprod"
    : "dev";
const meta = {
  appName: pkg.name ?? "web-next",
  version: pkg.version ?? "0.0.0",
  commit,
  timestamp,
  environmentRole,
  generatedBy: "scripts/generate-meta.mjs",
  nodeVersion: process.version,
};

const publicDir = path.join(projectRoot, "public");
mkdirSync(publicDir, { recursive: true });
const targetPath = path.join(publicDir, "meta.json");
writeFileSync(targetPath, JSON.stringify(meta, null, 2));

console.log(`[meta] Wrote ${targetPath} -> ${meta.version} (${meta.commit})`);

const modulesScript = path.join(projectRoot, "scripts", "generate-optional-modules.mjs");
safeExecFile("node", [modulesScript]);
