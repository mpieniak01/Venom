import { test, type Locator, type Page } from "@playwright/test";

type ReadinessResult = {
  ready: boolean;
  reasonCode: "runtime_model_unavailable" | "stack_degraded";
  details: string;
};

function isUnavailableModelLabel(label: string): boolean {
  return /Brak modeli|No models|Wybierz model|Choose model/i.test(label);
}

async function readLabel(locator: Locator): Promise<string> {
  return ((await locator.textContent()) ?? "").trim();
}

export async function ensureChatRuntimeReadyOrSkip(
  page: Page,
  timeoutMs = 8000,
): Promise<boolean> {
  // 197B policy for functional E2E:
  // if chat runtime/model precondition is missing, skip test with reason_code
  // instead of reporting false regression as fail.
  const modelButton = page.getByTestId("llm-model-select").first();
  if ((await modelButton.count()) === 0) {
    return true;
  }

  const deadline = Date.now() + timeoutMs;
  let latestLabel = "";
  let latestDisabled = false;
  while (Date.now() < deadline) {
    latestLabel = await readLabel(modelButton);
    latestDisabled = await modelButton.isDisabled();
    if (!latestDisabled && !isUnavailableModelLabel(latestLabel)) {
      return true;
    }
    await page.waitForTimeout(250);
  }

  const readiness: ReadinessResult = {
    ready: false,
    reasonCode: isUnavailableModelLabel(latestLabel)
      ? "runtime_model_unavailable"
      : "stack_degraded",
    details: `label="${latestLabel || "n/a"}", disabled=${String(latestDisabled)}`,
  };
  test.skip(
    true,
    `${readiness.reasonCode}: chat runtime model niegotowy (${readiness.details})`,
  );
  return false;
}
