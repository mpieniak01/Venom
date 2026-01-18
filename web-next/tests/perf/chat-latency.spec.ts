import { expect, test, type Page } from "@playwright/test";

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
  return `http://${host}:${port}`;
})();

const targets: TargetConfig[] = [
  {
    name: "Next Cockpit",
    url: process.env.PERF_NEXT_BASE_URL ?? defaultBaseUrl,
    promptSelector: '[data-testid="cockpit-prompt-input"]',
    sendSelector: '[data-testid="cockpit-send-button"]',
    responseSelector: '[data-testid="conversation-bubble-assistant"]',
    responseTimeoutMs: Number(process.env.PERF_NEXT_RESPONSE_TIMEOUT ?? "20000"),
    latencyBudgetMs: Number(process.env.PERF_NEXT_LATENCY_BUDGET ?? "5000"),
  },
  {
    name: "Legacy Cockpit",
    url: process.env.PERF_LEGACY_BASE_URL ?? "http://localhost:8000",
    promptSelector: "#taskInput",
    sendSelector: "#sendButton",
    responseSelector: ".chat-messages .message.assistant",
    responseTimeoutMs: Number(process.env.PERF_LEGACY_RESPONSE_TIMEOUT ?? "20000"),
    latencyBudgetMs: Number(process.env.PERF_LEGACY_LATENCY_BUDGET ?? "6000"),
    optional: true,
  },
];

async function measureLatency(page: Page, target: TargetConfig) {
  await page.goto(target.url);
  const prompt = `Benchmark latency ${Date.now()}`;
  const responseLocator = page.locator(target.responseSelector);
  const initialResponses = await responseLocator.count();

  try {
    // Attempt to fill with a shorter timeout (5s) to allow for error diagnosis within the test limit
    await page.fill(target.promptSelector, prompt, { timeout: 5_000 });
  } catch (error) {
    // 1. Check for application crash (Error Boundary)
    const errorBoundary = page.locator('[data-testid="app-error"]');
    if (await errorBoundary.count() > 0) {
      const errorText = await errorBoundary.innerText();
      throw new Error(`Aplikacja uległa awarii:\n${errorText}`);
    }

    // 2. Check for stuck loading state
    const loadingEl = page.locator("text=Ładowanie kokpitu");
    if (await loadingEl.count() > 0) {
      // Dump console logs if possible?
      throw new Error("Aplikacja utknęła na ekranie ładowania (isClientReady=false lub hydration error).");
    }

    // 3. Re-throw original error if we can't identify the cause
    throw error;
  }
  const sendButton = page.locator(target.sendSelector);
  await expect(sendButton).toBeEnabled({ timeout: 15000 });
  await sendButton.click();
  const start = performance.now();
  let latency: number | null = null;

  const expectedCount = initialResponses + 1;
  try {
    await expect
      .poll(async () => responseLocator.count(), {
        timeout: target.responseTimeoutMs ?? 30_000,
        message: `${target.name}: brak nowej odpowiedzi w strumieniu`,
      })
      .toBeGreaterThanOrEqual(expectedCount);
    latency = performance.now() - start;
  } catch (error) {
    if (target.optional) {
      test.skip(
        true,
        `${target.name} pominięty: brak odpowiedzi w ${target.responseTimeoutMs ?? 20_000}ms`,
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
