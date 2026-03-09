#!/usr/bin/env node

import {
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readlinkSync,
  readdirSync,
  rmSync,
  symlinkSync,
} from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.join(__dirname, "..");
const repoRoot = path.join(webRoot, "..");
const modulesRoot = path.join(repoRoot, "modules");
const webNodeModules = path.join(webRoot, "node_modules");
const webOptionalModulesRoot = path.join(webRoot, "optional-modules");

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

function ensureOptionalModuleWebMirror(moduleDir, moduleDirName) {
  const sourceWebPath = path.join(moduleDir, "web-next");
  if (!existsSync(sourceWebPath)) {
    return { status: "skip", reason: "module web-next folder missing" };
  }
  mkdirSync(webOptionalModulesRoot, { recursive: true });
  const targetPath = path.join(webOptionalModulesRoot, moduleDirName);

  try {
    if (existsSync(targetPath)) {
      rmSync(targetPath, { recursive: true, force: true });
    }
    cpSync(sourceWebPath, targetPath, { recursive: true, force: true, dereference: true });
    return { status: "synced" };
  } catch (error) {
    return { status: "skip", reason: String(error) };
  }
}

function removeInvalidOptionalModuleMirror(moduleDirName) {
  const targetPath = path.join(webOptionalModulesRoot, moduleDirName);
  if (!existsSync(targetPath)) {
    return;
  }
  try {
    const stat = lstatSync(targetPath);
    if (stat.isSymbolicLink()) {
      rmSync(targetPath, { recursive: true, force: true });
    }
  } catch (error) {
    console.warn(`[modules] skip stale mirror cleanup for ${moduleDirName}: ${String(error)}`);
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

  let createdNodeModules = 0;
  let reusedNodeModules = 0;
  let syncedWebMirrors = 0;
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

    const nodeModulesLinkResult = ensureModuleNodeModulesLink(moduleDir);
    if (nodeModulesLinkResult.status === "created") {
      createdNodeModules += 1;
    } else if (nodeModulesLinkResult.status === "ok") {
      reusedNodeModules += 1;
    } else {
      skipped.push(`${entry.name}: ${nodeModulesLinkResult.reason}`);
    }

    removeInvalidOptionalModuleMirror(entry.name);

    const webMirrorResult = ensureOptionalModuleWebMirror(moduleDir, entry.name);
    if (webMirrorResult.status === "synced") {
      syncedWebMirrors += 1;
    } else if (webMirrorResult.status === "skip" && webMirrorResult.reason) {
      skipped.push(`${entry.name}: ${webMirrorResult.reason}`);
    }
  }

  console.log(
    `[modules] optional module prep: node_modules(created=${createdNodeModules}, reused=${reusedNodeModules}), web-mirrors(synced=${syncedWebMirrors}), skipped=${skipped.length}`,
  );
  for (const item of skipped) {
    console.warn(`[modules] skip: ${item}`);
  }
}

main();
