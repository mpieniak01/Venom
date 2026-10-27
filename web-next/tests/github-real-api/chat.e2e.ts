import { expect, test } from "@playwright/test";

test("browser streams through the actual proxy and API to the controlled LLM", async ({ page, request }) => {
  const prompt = "GitHub E2E probe 4917";
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.documentElement.dataset.hydrated === "true");
  await page.waitForFunction(() => Boolean(localStorage.getItem("venom-session-id")));
  const mode = page.getByTestId("chat-mode-select");
  await expect(mode).toBeEnabled();
  await mode.scrollIntoViewIfNeeded();
  await mode.click();
  await page.getByTestId("chat-mode-option-direct").click();
  await page.getByTestId("cockpit-prompt-input").fill(prompt);
  const responsePromise = page.waitForResponse((response) =>
    response.url() === "http://127.0.0.1:13300/api/v1/llm/simple/stream" &&
    response.request().method() === "POST",
  );
  await expect(page.getByTestId("cockpit-send-button")).toBeEnabled();
  await page.getByTestId("cockpit-send-button").click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  await expect(page.getByTestId("conversation-bubble-assistant").last()).toContainText("VENOM_E2E_OK_42");
  const upstream = await request.get("http://127.0.0.1:11434/__ci_e2e__/calls");
  expect(upstream.ok()).toBeTruthy();
  const calls = await upstream.json();
  expect(calls.some((call: { model?: string; messages?: unknown }) =>
    call.model === "ci-fake-llm" && JSON.stringify(call.messages).includes(prompt),
  )).toBeTruthy();
});
