#!/usr/bin/env node

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

/** Read-only preflight; it never starts a server or activates a model. */
export async function evaluateE2ePreflight({ nextBase, apiBase, requireModel = false, fetcher = fetch, timeoutMs = 3000 }) {
  const unavailable = (reasonCode, message) => ({ ok: false, reasonCode, message });
  function isLoopbackUrl(value) {
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol) &&
        ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname) &&
        !url.username && !url.password && !url.search && !url.hash;
    } catch {
      return false;
    }
  }
  if (!isLoopbackUrl(nextBase) || !isLoopbackUrl(apiBase)) {
    return unavailable("target_not_local", "Panel i API muszą wskazywać lokalny komputer.");
  }
  async function request(url) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetcher(url, { method: "GET", signal: controller.signal, redirect: "error" });
    } finally {
      clearTimeout(timeout);
    }
  }

  let health;
  try {
    const response = await request(`${apiBase}/healthz`);
    if (!response.ok) return unavailable("stack_not_started", "API Venoma nie odpowiada poprawnie.");
    health = await response.json();
  } catch {
    return unavailable("stack_not_started", "API Venoma jest niedostępne.");
  }
  if (health?.component !== "venom-core" || health?.status !== "ok") {
    return unavailable("stack_degraded", "Odpowiedź healthz nie potwierdza tożsamości Venoma.");
  }
  try {
    const response = await request(nextBase);
    if (!response.ok) return unavailable("stack_not_started", "Panel Venoma jest niedostępny.");
  } catch {
    return unavailable("stack_not_started", "Panel Venoma jest niedostępny.");
  }

  if (!requireModel) return { ok: true, reasonCode: "ready", message: "Panel i API Venoma są dostępne." };

  try {
    const activeResponse = await request(`${apiBase}/api/v1/system/llm-servers/active`);
    if (!activeResponse.ok) return unavailable("stack_degraded", "Nie można odczytać aktywnego runtime.");
    const active = await activeResponse.json();
    if (!String(active?.active_server || "").trim() || !String(active?.active_model || "").trim()) {
      return unavailable("runtime_model_unavailable", "Brak aktywnego modelu; preflight go nie uruchamia.");
    }
    const resourcesResponse = await request(`${apiBase}/api/v1/system/models/resources`);
    if (!resourcesResponse.ok) return unavailable("stack_degraded", "Nie można odczytać dostępności runtime.");
    const resources = await resourcesResponse.json();
    const runtime = resources?.runtime;
    if (!runtime || !["available", "busy", "quarantined"].includes(runtime.status)) {
      return unavailable("stack_degraded", "Dostępność runtime nie została potwierdzona.");
    }
    if (runtime.status !== "available" || runtime.owner || Number(runtime.active_operations || 0) > 0) {
      return unavailable("runtime_busy", "Runtime jest zajęty lub wymaga odzyskania.");
    }
    return unavailable("proxy_identity_unverified", "Nie można potwierdzić, że panel używa sprawdzonego API; fizyczna generacja jest pominięta.");
  } catch {
    return unavailable("stack_degraded", "Nie można odczytać stanu runtime.");
  }
}

async function main() {
  const host = process.env.PLAYWRIGHT_HOST || "127.0.0.1";
  const port = process.env.PLAYWRIGHT_PORT || "3300";
  const nextBase = process.env.PERF_NEXT_BASE_URL || process.env.BASE_URL || `http://${host}:${port}`;
  const apiBase = (process.env.PERF_API_BASE || process.env.VENOM_API_BASE || "http://127.0.0.1:8800").replace(/\/$/, "");
  const result = await evaluateE2ePreflight({ nextBase, apiBase, requireModel: process.env.E2E_REQUIRE_MODEL === "1" });
  const stateFile = resolve(process.cwd(), process.env.E2E_PREFLIGHT_STATE_FILE || "test-results/e2e/preflight-state.json");
  mkdirSync(dirname(stateFile), { recursive: true });
  writeFileSync(stateFile, `${JSON.stringify({ timestamp: new Date().toISOString(), state: result.ok ? "ready" : result.reasonCode, reason_code: result.reasonCode, message: result.message }, null, 2)}\n`);
  if (!result.ok) {
    console.warn(`⏭️  E2E pominięte (${result.reasonCode}): ${result.message}`);
    process.exitCode = process.env.E2E_PREFLIGHT_STRICT === "1" ? 1 : 2;
    return;
  }
  console.log(`✅ E2E preflight: ${result.message}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch((error) => {
    console.error("E2E preflight failed:", error);
    process.exitCode = 1;
  });
}
