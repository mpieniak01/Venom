import { expect, test, type Page } from "@playwright/test";

type TargetConfig = {
  name: string;
  url: string;
  promptSelector: string;
  sendSelector: string;
  responseSelector: string;
  responseTimeoutMs?: number;
  latencyBudgetMs?: number;
};

const targets: TargetConfig[] = [
  {
    name: "Next Cockpit",
    url: process.env.PERF_NEXT_BASE_URL ?? "http://localhost:3000",
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
  },
];

async function measureLatency(page: Page, target: TargetConfig) {
  await page.goto(target.url);
  const prompt = `Benchmark latency ${Date.now()}`;
  const responseLocator = page.locator(target.responseSelector);
  const initialResponses = await responseLocator.count();

  await page.fill(target.promptSelector, prompt, { timeout: 10_000 });
  const sendButton = page.locator(target.sendSelector);
  await sendButton.click();
  const start = performance.now();

  const expectedCount = initialResponses + 1;
  await expect
    .poll(async () => responseLocator.count(), {
      timeout: target.responseTimeoutMs ?? 20_000,
      message: `${target.name}: brak nowej odpowiedzi w strumieniu`,
    })
    .toBeGreaterThanOrEqual(expectedCount);
  const latency = performance.now() - start;

  test.info().annotations.push({
    type: "latency",
    description: `${target.name}: ${latency.toFixed(0)}ms`,
  });

  const latencyBudgetMs = target.latencyBudgetMs ?? 5_000;
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
