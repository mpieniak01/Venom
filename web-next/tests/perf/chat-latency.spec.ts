import { expect, test, type Locator, type Page } from "@playwright/test";
import { buildHttpUrl } from "../utils/url";

type TargetConfig = {
  name: string;
  url: string;
  promptSelector: string;
  sendSelector: string;
  responseSelector: string;
  responseTimeoutMs?: number;
  latencyBudgetMs?: number;
  optional?: boolean;
};

const defaultBaseUrl = (() => {
  if (process.env.BASE_URL) return process.env.BASE_URL;
  const host = process.env.PLAYWRIGHT_HOST ?? "127.0.0.1";
  // Domyślnie celujemy w port Cockpitu (3000).
  const port = process.env.PLAYWRIGHT_PORT ?? "3000";
  const parsedPort = Number.parseInt(port, 10);
  return Number.isNaN(parsedPort) ? buildHttpUrl(host) : buildHttpUrl(host, parsedPort);
})();

const targets: TargetConfig[] = [
  {
    name: "Next Cockpit",
    url: process.env.PERF_NEXT_BASE_URL ?? defaultBaseUrl,
    promptSelector: '[data-testid="cockpit-prompt-input"]',
    sendSelector: '[data-testid="cockpit-send-button"]',
    responseSelector: '[data-testid="conversation-bubble-assistant"]',
    responseTimeoutMs: Number(process.env.PERF_NEXT_RESPONSE_TIMEOUT ?? "20000"),
    latencyBudgetMs: Number(process.env.PERF_NEXT_LATENCY_BUDGET ?? "15000"),
  },
];

const defaultApiBase =
  process.env.PERF_API_BASE ??
  process.env.VENOM_API_BASE ??
  buildHttpUrl("127.0.0.1", 8000);

async function isBackendHealthy() {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    const res = await fetch(`${defaultApiBase}/healthz`, {
      method: "GET",
      signal: controller.signal,
    });
    clearTimeout(timeout);
    return res.ok;
  } catch {
    return false;
  }
}

async function diagnosePromptFillError(page: Page, error: unknown): Promise<never> {
  const errorBoundary = page.locator('[data-testid="app-error"]');
  if (await errorBoundary.count() > 0) {
    const errorText = await errorBoundary.innerText();
    throw new Error(`Aplikacja uległa awarii:\n${errorText}`);
  }
  const loadingEl = page.locator("text=Ładowanie kokpitu");
  if (await loadingEl.count() > 0) {
    throw new Error("Aplikacja utknęła na ekranie ładowania (isClientReady=false lub hydration error).");
  }
  throw error;
}

async function fillPromptForTarget(page: Page, target: TargetConfig, prompt: string): Promise<boolean> {
  try {
    await page.fill(target.promptSelector, prompt, { timeout: 5_000 });
    return true;
  } catch (error) {
    if (target.optional) {
      test.skip(true, `${target.name} pominięty: brak pola promptu (${target.promptSelector})`);
      return false;
    }
    await diagnosePromptFillError(page, error);
    return false;
  }
}

async function waitForResponseLatency(
  page: Page,
  responseLocator: Locator,
  initialResponses: number,
  timeoutMs: number,
  targetName: string,
): Promise<number> {
  const deadline = Date.now() + timeoutMs;
  const startedAt = performance.now();
  let baseline = initialResponses;
  while (Date.now() < deadline) {
    const count = await responseLocator.count();
    if (count > baseline) {
      return performance.now() - startedAt;
    }
    if (count < baseline) {
      baseline = count;
    }
    await page.waitForTimeout(200);
  }
  throw new Error(`${targetName}: brak nowej odpowiedzi w strumieniu`);
}

async function measureLatency(page: Page, target: TargetConfig) {
  const backendOk = await isBackendHealthy();
  if (!backendOk) {
    test.skip(
      true,
      `Backend niedostępny pod ${defaultApiBase} (healthz). Pomijam test UI.`,
    );
    return;
  }
  await page.goto(target.url);
  const promptLocator = page.locator(target.promptSelector);
  try {
    await promptLocator.first().waitFor({ state: "visible", timeout: 3_000 });
  } catch (error) {
    if (target.optional) {
      test.skip(true, `${target.name} pominięty: brak selektora ${target.promptSelector}`);
      return;
    }
    throw error;
  }
  const prompt = `Benchmark latency ${Date.now()}`;
  const responseLocator = page.locator(target.responseSelector);
  const initialResponses = await responseLocator.count();

  const promptFilled = await fillPromptForTarget(page, target, prompt);
  if (!promptFilled) return;
  const sendButton = page.locator(target.sendSelector);
  await expect(sendButton).toBeEnabled({ timeout: 15000 });
  await sendButton.click();
  const timeoutMs = target.responseTimeoutMs ?? 30_000;
  let latency: number;
  try {
    latency = await waitForResponseLatency(page, responseLocator, initialResponses, timeoutMs, target.name);
  } catch (error) {
    if (target.optional) {
      test.skip(
        true,
        `${target.name} pominięty: brak odpowiedzi w ${timeoutMs}ms`,
      );
      return;
    }
    throw error;
  }

  test.info().annotations.push({
    type: "latency",
    description: `${target.name}: ${latency.toFixed(0)}ms`,
  });

  const latencyBudgetMs = target.latencyBudgetMs ?? 5_000;
  if (target.optional && latency > latencyBudgetMs) {
    test.skip(
      true,
      `${target.name} przekroczyl budzet ${latencyBudgetMs}ms (wynik: ${latency.toFixed(0)}ms)`,
    );
    return;
  }
  expect(latency, `${target.name}: przekroczono budżet ${latencyBudgetMs}ms`).toBeLessThanOrEqual(
    latencyBudgetMs,
  );
}

test.describe("latencja chatu", () => {
  for (const target of targets) {
    test(`latencja chatu – ${target.name}`, async ({ page }) => {
      test.skip(
        !target.url,
        `Brak adresu URL dla ${target.name} (ustaw PERF_NEXT_BASE_URL / PERF_LEGACY_BASE_URL)`,
      );
      await measureLatency(page, target);
    });
  }
});
