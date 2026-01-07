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
        await expect(page.getByText("Statystyki Lekcji")).toBeVisible();
        await expect(page.getByText("Automatyczna Higiena")).toBeVisible();
    });

    test("should display pruning controls", async ({ page }) => {
        await page.goto("/brain");
        await page.getByTestId("hygiene-tab").click();

        // Check for specific buttons/inputs
        await expect(page.getByPlaceholder("Dni (np. 30)")).toBeVisible();
        await expect(page.getByPlaceholder("Nazwa tagu")).toBeVisible();

        // Verify actions buttons exist
        await expect(page.getByRole("button", { name: "Deduplikacja" })).toBeVisible();
        await expect(page.getByRole("button", { name: "Nuke All" })).toBeVisible();
    });
});
