#!/usr/bin/env node

/**
 * Simple preflight check for E2E tests.
 * Verifies that required services (Next Cockpit) are reachable before Playwright runs.
 * Legacy Cockpit is optional: if unavailable, we print a warning.
 */

const DEFAULT_HOST = process.env.PLAYWRIGHT_HOST ?? "127.0.0.1";
const DEFAULT_PORT = process.env.PLAYWRIGHT_PORT ?? "3000";
const defaultNextUrl = process.env.PERF_NEXT_BASE_URL ?? `http://${DEFAULT_HOST}:${DEFAULT_PORT}`;
const legacyUrl = process.env.PERF_LEGACY_BASE_URL ?? "http://localhost:8000";

const targets = [
  { name: "Next Cockpit", url: defaultNextUrl, required: true },
  { name: "Legacy Cockpit", url: legacyUrl, required: false },
];

const timeoutMs = 3000;

async function checkTarget(target) {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(target.url, { method: "GET", signal: controller.signal });
    clearTimeout(t);
    return res.ok || res.status < 500; // we only need the server to respond
  } catch {
    clearTimeout(t);
    return false;
  }
}

async function main() {
  let hardFail = false;
  console.log("🔎 Preflight: sprawdzanie dostępności usług dla testów E2E...\n");
  for (const target of targets) {
    const ok = await checkTarget(target);
    if (ok) {
      console.log(`✅ ${target.name} osiągalny pod ${target.url}`);
    } else if (target.required) {
      console.error(
        `❌ ${target.name} nieosiągalny pod ${target.url}. Uruchom backend/frontend przed testami (np. Next dev na porcie 3000).`
      );
      hardFail = true;
    } else {
      console.warn(
        `⚠️  ${target.name} (opcjonalny) nieosiągalny pod ${target.url}. Testy mogą pominąć Legacy lub zakończyć się błędem.`
      );
    }
  }
  if (hardFail) {
    console.error("\nPrzerwano: wymagane usługi nie działają.");
    process.exit(1);
  } else {
    console.log("\nPreflight OK. Uruchamiam testy...");
  }
}

main().catch((err) => {
  console.error("Preflight check failed:", err);
  process.exit(1);
});
