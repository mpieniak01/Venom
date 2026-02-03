import { expect, test } from "@playwright/test";

test.describe("Brain Hygiene Tab", () => {
    test("should be accessible from Brain view", async ({ page }) => {
        // 1. Go to Brain
        await page.goto("/brain");

        // 2. Find hygiene tab using data-testid for more reliable selection
        const hygieneTab = page.getByTestId("hygiene-tab");

        // Ensure tab button exists
        await expect(hygieneTab).toBeVisible();

        // 3. Click tab
        await hygieneTab.click();

        // 4. Verify panel content loads
        await expect(page.getByText("Lesson Statistics")).toBeVisible();
        await expect(page.getByText("Auto Hygiene")).toBeVisible();
    });

    test("should display pruning controls", async ({ page }) => {
        await page.goto("/brain");
        await page.getByTestId("hygiene-tab").click();

        // Check for specific buttons/inputs
        await expect(page.getByPlaceholder("Days (e.g. 30)")).toBeVisible();
        await expect(page.getByPlaceholder("Tag name")).toBeVisible();

        // Verify actions buttons exist (using button text, not label)
        await expect(page.getByRole("button", { name: "Run" })).toBeVisible();
        await expect(page.getByRole("button", { name: "Clear" })).toBeVisible();
    });
});
