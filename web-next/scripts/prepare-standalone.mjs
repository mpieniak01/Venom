#!/usr/bin/env node
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";

if (process.env.SKIP_PREPARE_STANDALONE === "1") {
  console.log("[prepare-standalone] Pominięto (SKIP_PREPARE_STANDALONE=1).");
  process.exit(0);
}

const distDir = process.env.NEXT_DIST_DIR || ".next";
const rootDir = path.join(process.cwd());
const staticSrc = path.join(rootDir, distDir, "static");
const standaloneTargets = [
  // Next standalone commonly expects static under standalone/<app>/.next/static
  path.join(rootDir, distDir, "standalone", "web-next", distDir, "static"),
  // Backward-compatible fallback for previously used layout
  path.join(rootDir, distDir, "standalone", distDir, "static"),
];

if (!existsSync(staticSrc)) {
  console.warn("[prepare-standalone] Pomijam kopiowanie – brak katalogu .next/static (uruchom najpierw `npm run build`).");
  process.exit(0);
}

for (const target of standaloneTargets) {
  mkdirSync(path.dirname(target), { recursive: true });
  if (existsSync(target)) {
    rmSync(target, { recursive: true, force: true });
  }
  cpSync(staticSrc, target, { recursive: true });
  console.log(`[prepare-standalone] Skopiowano .next/static do ${target}.`);
}
