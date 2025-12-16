#!/usr/bin/env node
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";

const rootDir = path.join(process.cwd());
const staticSrc = path.join(rootDir, ".next", "static");
const standaloneTarget = path.join(rootDir, ".next", "standalone", ".next", "static");

if (!existsSync(staticSrc)) {
  console.warn("[prepare-standalone] Pomijam kopiowanie – brak katalogu .next/static (uruchom najpierw `npm run build`).");
  process.exit(0);
}

mkdirSync(path.dirname(standaloneTarget), { recursive: true });
if (existsSync(standaloneTarget)) {
  rmSync(standaloneTarget, { recursive: true, force: true });
}

cpSync(staticSrc, standaloneTarget, { recursive: true });
console.log("[prepare-standalone] Skopiowano .next/static do .next/standalone/.next/static.");
