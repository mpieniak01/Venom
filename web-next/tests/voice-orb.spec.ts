import { expect, test } from "@playwright/test";

test.describe("Voice controls with disabled audio", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("venom-language", "pl");
    });
    await page.route("**/api/v1/audio/status", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: false,
          connected_clients: 0,
          active_recordings: 0,
        }),
      }),
    );
    await page.route("**/api/v1/system/llm-runtime/options**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "success", active: null, runtimes: [] }),
      }),
    );
  });

  test("voice page keeps text controls visible and hides the orb when audio is disabled", async ({ page }) => {
    await page.goto("/voice", { waitUntil: "domcontentloaded" });

    // The disabled-audio fixture keeps the page in text mode.
    const toggleButton = page.getByTestId("voice-mode-toggle").getByRole("button", { name: "Text", exact: true });
    await toggleButton.waitFor({ state: "visible", timeout: 10000 });
    await expect(toggleButton).toBeVisible();

    await expect(toggleButton).toBeDisabled();
    await expect(page.getByText("Kanał audio wyłączony w konfiguracji.", { exact: true })).toBeVisible();
    await expect(page.locator("[data-orb-state]")).toHaveCount(0);
  });

  test("voice page keeps disabled-audio controls visible without an orb", async ({ page }) => {
    await page.goto("/voice", { waitUntil: "domcontentloaded" });

    // The recording control stays visible, but disabled, in text mode.
    const pttButton = page.getByRole("button", { name: "🎙 Czat tekstowy", exact: true });
    await pttButton.waitFor({ state: "visible", timeout: 10000 });

    await expect(pttButton).toBeDisabled();

    // The text-mode toggle remains visible even though audio is disabled.
    const toggleButton = page.getByTestId("voice-mode-toggle").getByRole("button", { name: "Text", exact: true });
    await expect(toggleButton).toBeVisible();

    // TTS mute button must be visible
    const ttsButton = page.getByRole("button", { name: "TTS: on", exact: true });
    await expect(ttsButton).toBeVisible();
    await expect(ttsButton).toBeDisabled();
  });

  test("voice page desktop layout - disabled-audio controls stay visible", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/voice", { waitUntil: "domcontentloaded" });

    const pttButton = page.getByRole("button", { name: "🎙 Czat tekstowy", exact: true });
    await pttButton.waitFor({ state: "visible", timeout: 10000 });
    await expect(pttButton).toBeVisible();
    await expect(pttButton).toBeDisabled();
    await page.screenshot({ path: "test-results/voice-orb-desktop.png", fullPage: false });
  });

  test("voice page mobile layout - disabled-audio controls stay visible", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/voice", { waitUntil: "domcontentloaded" });

    const pttButton = page.getByRole("button", { name: "🎙 Czat tekstowy", exact: true });
    await pttButton.waitFor({ state: "visible", timeout: 10000 });
    await expect(pttButton).toBeVisible();
    await expect(pttButton).toBeDisabled();
    await page.screenshot({ path: "test-results/voice-orb-mobile.png", fullPage: false });
  });
});
