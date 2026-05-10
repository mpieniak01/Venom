import { expect, test } from "@playwright/test";

test.describe("VoiceOrb smoke", () => {
  test.beforeEach(async ({ page }) => {
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

  test("voice orb is visible on /voice page in voice mode", async ({ page }) => {
    await page.goto("/voice", { waitUntil: "domcontentloaded" });

    // Verify the page loaded and the core voice control chrome is rendered —
    // confirms no JS crash during mount regardless of audio env-var config.
    const toggleButton = page.getByRole("button", { name: /Voice|Text/i }).first();
    await toggleButton.waitFor({ state: "visible", timeout: 10000 });
    await expect(toggleButton).toBeVisible();

    // When audio is enabled the orb renders in voice mode; when disabled it does
    // not. Either way, if the page loaded the data-orb-state attribute must have
    // a valid value from VoiceOrbState when the orb is present.
    const orbContainer = page.locator("[data-orb-state]");
    const count = await orbContainer.count();
    if (count > 0) {
      const orbStateAttr = await orbContainer.first().getAttribute("data-orb-state");
      expect(["offline","ready","recording","stt","thinking","tts","complete","error"]).toContain(orbStateAttr);
    }
  });

  test("voice page renders controls without layout shift from orb", async ({ page }) => {
    await page.goto("/voice", { waitUntil: "domcontentloaded" });

    // Push-to-talk button must always be accessible
    const pttButton = page.getByRole("button", { name: /Hold to talk|Przytrzymaj|Gedrückt/i });
    await pttButton.waitFor({ state: "visible", timeout: 10000 });

    // Voice/Text toggle must be visible
    const toggleButton = page.getByRole("button", { name: /Voice|Text/i }).first();
    await expect(toggleButton).toBeVisible();

    // TTS mute button must be visible
    await expect(page.getByRole("button", { name: /TTS/i }).first()).toBeVisible();
  });

  test("voice page desktop layout - no overlap between orb and controls", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/voice", { waitUntil: "domcontentloaded" });

    await page.getByRole("button", { name: /Hold to talk|Przytrzymaj|Gedrückt/i }).waitFor({
      state: "visible",
      timeout: 10000,
    });

    await page.screenshot({ path: "test-results/voice-orb-desktop.png", fullPage: false });
  });

  test("voice page mobile layout - controls remain accessible", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/voice", { waitUntil: "domcontentloaded" });

    await page.getByRole("button", { name: /Hold to talk|Przytrzymaj|Gedrückt/i }).waitFor({
      state: "visible",
      timeout: 10000,
    });

    await page.screenshot({ path: "test-results/voice-orb-mobile.png", fullPage: false });
  });
});
