#!/usr/bin/env node

import { existsSync, lstatSync, readdirSync, readlinkSync, symlinkSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.join(__dirname, "..");
const repoRoot = path.join(webRoot, "..");
const modulesRoot = path.join(repoRoot, "modules");
const webNodeModules = path.join(webRoot, "node_modules");

function ensureModuleNodeModulesLink(moduleDir) {
  const targetPath = path.join(moduleDir, "node_modules");
  const relativeTarget = path.relative(moduleDir, webNodeModules);

  if (!existsSync(targetPath)) {
    symlinkSync(relativeTarget, targetPath, "dir");
    return { status: "created", moduleDir, targetPath, relativeTarget };
  }

  try {
    const stat = lstatSync(targetPath);
    if (stat.isSymbolicLink()) {
      const existing = readlinkSync(targetPath);
      if (existing === relativeTarget) {
        return { status: "ok", moduleDir, targetPath, relativeTarget };
      }
      return {
        status: "skip",
        moduleDir,
        targetPath,
        reason: `existing symlink points to ${existing}`,
      };
    }
    return {
      status: "skip",
      moduleDir,
      targetPath,
      reason: "path exists and is not a symlink",
    };
  } catch (error) {
    return {
      status: "skip",
      moduleDir,
      targetPath,
      reason: String(error),
    };
  }
}

function main() {
  if (!existsSync(modulesRoot)) {
    console.log("[modules] modules workspace not found, skipping node_modules link prep.");
    return;
  }

  if (!existsSync(webNodeModules)) {
    console.log("[modules] web-next/node_modules missing, skipping node_modules link prep.");
    return;
  }

  let created = 0;
  let reused = 0;
  const skipped = [];

  for (const entry of readdirSync(modulesRoot, { withFileTypes: true })) {
    if (!entry.isDirectory()) {
      continue;
    }

    const moduleDir = path.join(modulesRoot, entry.name);
    const moduleWebDir = path.join(moduleDir, "web-next");
    if (!existsSync(moduleWebDir)) {
      continue;
    }

    const result = ensureModuleNodeModulesLink(moduleDir);
    if (result.status === "created") {
      created += 1;
    } else if (result.status === "ok") {
      reused += 1;
    } else {
      skipped.push(`${entry.name}: ${result.reason}`);
    }
  }

  console.log(
    `[modules] optional module node_modules prep: created=${created}, reused=${reused}, skipped=${skipped.length}`,
  );
  for (const item of skipped) {
    console.warn(`[modules] skip: ${item}`);
  }
}

main();
