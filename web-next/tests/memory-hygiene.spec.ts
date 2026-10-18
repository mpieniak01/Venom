import { expect, test } from "@playwright/test";

test.describe("Brain Hygiene Tab", () => {
    test.beforeEach(async ({ page }) => {
        await page.goto("/brain");
        await expect(page.locator("html")).toHaveAttribute("data-hydrated", "true");

        // Choose the UI language after hydration instead of relying on bootstrap storage.
        await page.getByRole("button", {
            name: /Przełącz język|Switch language|Sprache wechseln/i,
        }).click();
        await page.getByRole("button", { name: "EN English", exact: true }).click();
        await expect(page.locator("html")).toHaveAttribute("lang", "en");
    });

    test("should be accessible from Brain view", async ({ page }) => {
        // Find the hygiene tab after the shared navigation and language setup.
        const hygieneTab = page.getByTestId("hygiene-tab");

        // Ensure tab button exists
        await expect(hygieneTab).toBeVisible();

        // 3. Click tab
        await hygieneTab.click();

        // 4. Verify panel content loads
        await expect(page.getByRole("heading", { name: "Lesson Statistics", exact: true })).toBeVisible();
        await expect(page.getByRole("heading", { name: "Auto Hygiene", exact: true })).toBeVisible();
    });

    test("should display pruning controls", async ({ page }) => {
        await page.getByTestId("hygiene-tab").click();

        // Check for specific buttons/inputs
        await expect(page.getByPlaceholder("Days (e.g. 30)")).toBeVisible();
        await expect(page.getByPlaceholder("Tag name")).toBeVisible();

        // Verify actions buttons exist (using button text, not label)
        await expect(page.getByRole("button", { name: "Run", exact: true })).toBeVisible();
        await expect(page.getByRole("button", { name: "Clear", exact: true })).toBeVisible();
    });
});
