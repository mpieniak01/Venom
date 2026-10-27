import { expect, test, type Locator, type Page } from "@playwright/test";
import { buildHttpUrl } from "../utils/url";
import { evaluateE2ePreflight } from "../../scripts/check-e2e-env.mjs";

type TargetConfig = {
  name: string;
  url: string;
  promptSelector: string;
  sendSelector: string;
  responseSelector: string;
  responseTimeoutMs?: number;
  latencyBudgetMs?: number;
};

const defaultBaseUrl = (() => {
  if (process.env.BASE_URL) return process.env.BASE_URL;
  const host = process.env.PLAYWRIGHT_HOST ?? "127.0.0.1";
  // Lokalnie korzystamy z istniejącego panelu Venoma.
  const port = process.env.PLAYWRIGHT_PORT ?? "3300";
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
    responseTimeoutMs: Number(process.env.PERF_NEXT_RESPONSE_TIMEOUT ?? "60000"),
    latencyBudgetMs: Number(process.env.PERF_NEXT_LATENCY_BUDGET ?? "45000"),
  },
];

const defaultApiBase =
  process.env.PERF_API_BASE ??
  process.env.VENOM_API_BASE ??
  buildHttpUrl("127.0.0.1", 8800);

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
    await diagnosePromptFillError(page, error);
    return false;
  }
}

async function ensureChatRuntimeReady(page: Page, target: TargetConfig): Promise<boolean> {
  const modelButton = page.getByTestId("llm-model-select");
  if ((await modelButton.count()) === 0) {
    throw new Error("Brak kontrolki aktywnego modelu w gotowym panelu.");
  }
  const button = modelButton.first();
  const waitDeadline = Date.now() + 20_000;
  let label = "";
  let isDisabled = true;
  let isUnavailable = true;

  while (Date.now() < waitDeadline) {
    label = ((await button.textContent()) ?? "").trim();
    isDisabled = await button.isDisabled();
    isUnavailable = /Brak modeli|No models|Wybierz model|Choose model/i.test(label);
    if (!isDisabled && !isUnavailable) {
      return true;
    }
    try {
      await page.waitForFunction(
        ({ previousLabel, previousDisabled }) => {
          const candidate = document.querySelector<HTMLButtonElement>('[data-testid="llm-model-select"]');
          if (!candidate) return true;
          const disabled = candidate.disabled || candidate.getAttribute("aria-disabled") === "true";
          return (candidate.textContent ?? "").trim() !== previousLabel || disabled !== previousDisabled;
        },
        { previousLabel: label, previousDisabled: isDisabled },
        { timeout: Math.max(1, waitDeadline - Date.now()) },
      );
    } catch (error) {
      if (!(error instanceof Error) || error.name !== "TimeoutError") throw error;
      break;
    }
  }

  if (isDisabled || isUnavailable) {
    throw new Error(
      `${target.name}: brak aktywnego modelu czatu (label="${label || "n/a"}", disabled=${String(isDisabled)})`,
    );
  }
  return true;
}

async function waitForResponseLatency(
  responseLocator: Locator,
  initialResponses: number,
  timeoutMs: number,
  targetName: string,
): Promise<number> {
  const startedAt = performance.now();
  let baseline = initialResponses;
  try {
    await expect.poll(async () => {
      const count = await responseLocator.count();
      if (count > baseline) return true;
      if (count < baseline) baseline = count;
      return false;
    }, { timeout: timeoutMs, intervals: [50] }).toBe(true);
    return performance.now() - startedAt;
  } catch (error) {
    const responseTexts = await responseLocator.allTextContents().catch(() => []);
    const latestText = (responseTexts.at(-1) ?? "").trim();
    throw new Error(
      `${targetName}: brak nowej odpowiedzi w strumieniu (assistant_count=${baseline}, latest_assistant="${latestText.slice(0, 120)}")`,
      { cause: error },
    );
  }
}

async function measureLatency(page: Page, target: TargetConfig) {
  const readiness = await evaluateE2ePreflight({
    nextBase: target.url,
    apiBase: defaultApiBase.replace(/\/$/, ""),
    requireModel: true,
  });
  if (!readiness.ok) {
    test.skip(true, `${readiness.reasonCode}: ${readiness.message}`);
    return;
  }
  await page.goto(target.url);
  const promptLocator = page.locator(target.promptSelector);
  await promptLocator.first().waitFor({ state: "visible", timeout: 3_000 });
  const prompt = `Benchmark latency ${Date.now()}`;
  const responseLocator = page.locator(target.responseSelector);
  const initialResponses = await responseLocator.count();

  const runtimeReady = await ensureChatRuntimeReady(page, target);
  if (!runtimeReady) return;

  const promptFilled = await fillPromptForTarget(page, target, prompt);
  if (!promptFilled) return;
  const sendButton = page.locator(target.sendSelector);
  await expect(sendButton).toBeEnabled({ timeout: 15000 });
  await sendButton.click();
  const timeoutMs = target.responseTimeoutMs ?? 30_000;
  const latency = await waitForResponseLatency(responseLocator, initialResponses, timeoutMs, target.name);

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
  test.setTimeout(120_000);
  for (const target of targets) {
    test(`latencja chatu – ${target.name}`, async ({ page }) => {
      test.skip(
        !target.url,
        `Brak adresu URL dla ${target.name} (ustaw PERF_NEXT_BASE_URL lub BASE_URL)`,
      );
      await measureLatency(page, target);
    });
  }
});

test.describe("diagnostyka timeoutu odpowiedzi", () => {
  test.setTimeout(10_000);

  test("brak elementu odpowiedzi nie uruchamia kolejnego oczekiwania", async ({ page }) => {
    await page.setContent("<main>Brak odpowiedzi</main>");
    const responseLocator = page.getByTestId("conversation-bubble-assistant");

    await expect(waitForResponseLatency(responseLocator, 0, 25, "Diagnostyka")).rejects.toMatchObject({
      message: 'Diagnostyka: brak nowej odpowiedzi w strumieniu (assistant_count=0, latest_assistant="")',
      cause: expect.any(Error),
    });
  });

  test("zapisuje ostatnią istniejącą treść po wygaśnięciu limitu", async ({ page }) => {
    await page.setContent(`
      <div data-testid="conversation-bubble-assistant">Poprzednia odpowiedź</div>
      <div data-testid="conversation-bubble-assistant">  Ostatnia odpowiedź  </div>
    `);
    const responseLocator = page.getByTestId("conversation-bubble-assistant");

    await expect(waitForResponseLatency(responseLocator, 2, 25, "Diagnostyka")).rejects.toMatchObject({
      message: 'Diagnostyka: brak nowej odpowiedzi w strumieniu (assistant_count=2, latest_assistant="Ostatnia odpowiedź")',
      cause: expect.any(Error),
    });
  });
});
