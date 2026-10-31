import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, symlinkSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const defaultRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/** Reuse the installed Full dependency tree; never install or prepare modules. */
export function prepareStudio(appRoot = defaultRoot) {
  const repositoryRoot = path.dirname(appRoot);
  const sharedModules = path.join(repositoryRoot, "web-next", "node_modules");
  if (!existsSync(path.join(sharedModules, "next", "package.json"))) {
    throw new Error("Studio requires the existing web-next/node_modules dependency tree");
  }
  const captureWorklet = readFileSync(path.join(repositoryRoot, "web-next", "public", "chat2-capture-worklet.js"));
  const appModules = path.join(appRoot, "node_modules");
  if (!existsSync(appModules)) symlinkSync(path.relative(appRoot, sharedModules), appModules, "dir");
  const pkg = JSON.parse(readFileSync(path.join(appRoot, "package.json"), "utf8"));
  let commit = "unknown";
  try {
    commit = execFileSync("git", ["rev-parse", "--short", "HEAD"], {
      cwd: repositoryRoot, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch { /* Packaged artifacts may omit Git metadata. */ }
  const role = (process.env.ENVIRONMENT_ROLE || "dev").trim().toLowerCase();
  const metadata = {
    appName: pkg.name, version: pkg.version, commit,
    timestamp: new Date().toISOString(), environmentRole: role === "preprod" ? "preprod" : "dev",
    generatedBy: "web-studio/scripts/prepare-studio.mjs", nodeVersion: process.version,
  };
  const publicDir = path.join(appRoot, "public");
  mkdirSync(publicDir, { recursive: true });
  writeFileSync(path.join(publicDir, "chat2-capture-worklet.js"), captureWorklet);
  writeFileSync(path.join(publicDir, "meta.json"), JSON.stringify(metadata, null, 2) + "\n");
  return metadata;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const metadata = prepareStudio();
  console.log(`[studio] Reusing web-next dependencies; ${metadata.version} (${metadata.commit})`);
}
