#!/usr/bin/env node

/**
 * E2E preflight check.
 * Verifies that required services (Next Cockpit) are reachable before Playwright runs.
 * Uses retries and accepts both 127.0.0.1/localhost variants to reduce false negatives.
 */

const DEFAULT_HOST = process.env.PLAYWRIGHT_HOST ?? "127.0.0.1";
const DEFAULT_PORT = process.env.PLAYWRIGHT_PORT ?? "3000";
const defaultNextUrl = process.env.PERF_NEXT_BASE_URL ?? process.env.BASE_URL ?? `http://${DEFAULT_HOST}:${DEFAULT_PORT}`;
const fallbackLocalhostUrl = `http://localhost:${DEFAULT_PORT}`;
const targets = [
  {
    name: "Next Cockpit",
    urls: [...new Set([defaultNextUrl, fallbackLocalhostUrl])],
    required: true,
  },
];

const timeoutMs = Number(process.env.E2E_PREFLIGHT_TIMEOUT_MS ?? 3000);
const retries = Number(process.env.E2E_PREFLIGHT_RETRIES ?? 10);
const retryDelayMs = Number(process.env.E2E_PREFLIGHT_RETRY_DELAY_MS ?? 1000);
const strictPreflight =
  process.env.E2E_PREFLIGHT_STRICT === "1" || process.env.CI === "true";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function checkUrl(url) {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { method: "GET", signal: controller.signal });
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
    let matchedUrl = "";
    for (let attempt = 1; attempt <= retries; attempt += 1) {
      for (const url of target.urls) {
        const ok = await checkUrl(url);
        if (ok) {
          matchedUrl = url;
          break;
        }
      }
      if (matchedUrl) break;
      if (attempt < retries) {
        await sleep(retryDelayMs);
      }
    }

    if (matchedUrl) {
      console.log(`✅ ${target.name} osiągalny pod ${matchedUrl}`);
    } else if (target.required) {
      console.error(
        `❌ ${target.name} nieosiągalny pod: ${target.urls.join(", ")}. ` +
          `Uruchom frontend (np. Next dev na porcie ${DEFAULT_PORT}) i upewnij się, że odpowiada z tego samego środowiska, z którego uruchamiasz testy.`
      );
      hardFail = true;
    } else {
      console.warn(
        `⚠️  ${target.name} (opcjonalny) nieosiągalny pod: ${target.urls.join(", ")}. Testy mogą pominąć Legacy lub zakończyć się błędem.`
      );
    }
  }
  if (hardFail) {
    if (strictPreflight) {
      console.error("\nPrzerwano: wymagane usługi nie działają.");
      process.exit(1);
    }
    console.warn(
      "\n⏭️  E2E preflight niespełniony: pomijam testy E2E (tryb non-strict). " +
        "Ustaw E2E_PREFLIGHT_STRICT=1, aby wymusić błąd."
    );
    process.exit(2);
  } else {
    console.log("\nPreflight OK. Uruchamiam testy...");
  }
}

main().catch((err) => {
  console.error("Preflight check failed:", err);
  process.exit(1);
});
