#!/usr/bin/env node

/**
 * E2E preflight check.
 * Verifies that required services (Next Cockpit + backend API) are reachable before Playwright runs.
 * Uses retries and accepts both 127.0.0.1/localhost variants to reduce false negatives.
 */

const DEFAULT_HOST = process.env.PLAYWRIGHT_HOST ?? "127.0.0.1";
const DEFAULT_PORT = process.env.PLAYWRIGHT_PORT ?? "3000";
const defaultNextUrl = process.env.PERF_NEXT_BASE_URL ?? process.env.BASE_URL ?? `http://${DEFAULT_HOST}:${DEFAULT_PORT}`;
const fallbackLocalhostUrl = `http://localhost:${DEFAULT_PORT}`;
const defaultApiBase =
  process.env.PERF_API_BASE ??
  process.env.VENOM_API_BASE ??
  "http://127.0.0.1:8000";
const targets = [
  {
    name: "Next Cockpit",
    urls: [...new Set([defaultNextUrl, fallbackLocalhostUrl])],
    required: true,
  },
  {
    name: "Backend API",
    urls: [`${defaultApiBase}/healthz`],
    required: true,
  },
];

const timeoutMs = Number(process.env.E2E_PREFLIGHT_TIMEOUT_MS ?? 3000);
const retries = Number(process.env.E2E_PREFLIGHT_RETRIES ?? 10);
const retryDelayMs = Number(process.env.E2E_PREFLIGHT_RETRY_DELAY_MS ?? 1000);
const strictPreflight =
  process.env.E2E_PREFLIGHT_STRICT === "1" || process.env.CI === "true";
const apiPrefix = `${defaultApiBase}/api/v1`;

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

async function fetchJson(url, options = {}) {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        "content-type": "application/json",
        ...(options.headers ?? {}),
      },
    });
    const text = await res.text();
    const payload = text ? JSON.parse(text) : null;
    return { ok: res.ok, status: res.status, payload };
  } finally {
    clearTimeout(t);
  }
}

function getModelId(model) {
  if (!model || typeof model !== "object") return "";
  return String(model.id ?? model.name ?? model.model_id ?? "").trim();
}

function resolveActivationCandidate(optionsPayload) {
  const runtimes = Array.isArray(optionsPayload?.runtimes) ? optionsPayload.runtimes : [];
  const chatModels = Array.isArray(optionsPayload?.model_catalog?.chat_models)
    ? optionsPayload.model_catalog.chat_models
    : [];
  const preferredRuntimeOrder = ["ollama", "vllm", "onnx"];

  const runtimeCandidates = runtimes
    .filter((runtime) =>
      runtime &&
      runtime.source_type === "local-runtime" &&
      runtime.available !== false &&
      runtime.configured !== false,
    )
    .sort((a, b) => {
      const aIdx = preferredRuntimeOrder.indexOf(String(a.runtime_id ?? "").toLowerCase());
      const bIdx = preferredRuntimeOrder.indexOf(String(b.runtime_id ?? "").toLowerCase());
      return (aIdx === -1 ? 999 : aIdx) - (bIdx === -1 ? 999 : bIdx);
    });

  for (const runtime of runtimeCandidates) {
    const runtimeId = String(runtime.runtime_id ?? "").trim().toLowerCase();
    if (!runtimeId) continue;
    const runtimeModels = Array.isArray(runtime.models) ? runtime.models : [];
    const fromRuntime = runtimeModels.find(
      (model) => model?.chat_compatible !== false && getModelId(model),
    );
    if (fromRuntime) {
      return { serverName: runtimeId, model: getModelId(fromRuntime) };
    }
    const fromCatalog = chatModels.find(
      (model) =>
        String(model?.runtime_id ?? "").trim().toLowerCase() === runtimeId &&
        model?.chat_compatible !== false &&
        getModelId(model),
    );
    if (fromCatalog) {
      return { serverName: runtimeId, model: getModelId(fromCatalog) };
    }
  }

  return null;
}

async function ensureActiveChatModel() {
  const activeResponse = await fetchJson(`${apiPrefix}/system/llm-servers/active`);
  if (!activeResponse.ok) {
    throw new Error(
      `Nie udało się odczytać aktywnego runtime LLM (${activeResponse.status}).`,
    );
  }

  const activeServer = String(activeResponse.payload?.active_server ?? "").trim();
  const activeModel = String(activeResponse.payload?.active_model ?? "").trim();
  if (activeServer && activeModel) {
    console.log(`✅ Aktywny model czatu: ${activeServer} / ${activeModel}`);
    return;
  }

  console.log("ℹ️  Brak aktywnego modelu czatu. Próba automatycznej aktywacji...");
  const optionsResponse = await fetchJson(`${apiPrefix}/system/llm-runtime/options`);
  if (!optionsResponse.ok) {
    throw new Error(
      `Nie udało się pobrać opcji runtime LLM (${optionsResponse.status}).`,
    );
  }

  const candidate = resolveActivationCandidate(optionsResponse.payload);
  if (!candidate) {
    throw new Error(
      "Brak dostępnego lokalnego modelu czatu do aktywacji. Uruchom lub zainstaluj model lokalny przed E2E.",
    );
  }

  const activateResponse = await fetchJson(`${apiPrefix}/system/llm-servers/active`, {
    method: "POST",
    body: JSON.stringify({
      server_name: candidate.serverName,
      model: candidate.model,
    }),
  });
  if (!activateResponse.ok) {
    const detail = activateResponse.payload?.detail
      ? ` detail=${JSON.stringify(activateResponse.payload.detail)}`
      : "";
    throw new Error(
      `Nie udało się aktywować modelu czatu ${candidate.serverName}/${candidate.model} (${activateResponse.status}).${detail}`,
    );
  }

  const resolvedServer = String(activateResponse.payload?.active_server ?? candidate.serverName).trim();
  const resolvedModel = String(activateResponse.payload?.active_model ?? candidate.model).trim();
  if (!resolvedModel) {
    throw new Error(
      `Aktywacja runtime ${candidate.serverName} zakończyła się bez aktywnego modelu.`,
    );
  }
  console.log(`✅ Aktywowano model czatu: ${resolvedServer} / ${resolvedModel}`);
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
        `⚠️  ${target.name} (opcjonalny) nieosiągalny pod: ${target.urls.join(", ")}. Testy mogą zostać pominięte lub zakończyć się błędem.`
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
    await ensureActiveChatModel();
    console.log("\nPreflight OK. Uruchamiam testy...");
  }
}

main().catch((err) => {
  console.error("Preflight check failed:", err);
  process.exit(1);
});
