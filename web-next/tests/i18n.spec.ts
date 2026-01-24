import { test, expect } from "@playwright/test";

test.describe("Internationalization (i18n)", () => {
    test("should switch languages and update UI content", async ({ page }) => {
        // 1. Start at home page
        await page.goto("/");

        // Wait for hydration/rendering
        await expect(page.getByTestId("topbar-command-center")).toBeVisible();

        // 2. Check default language (PL)
        // "Centrum dowodzenia" is the PL translation for "Command Center" in TopBar button
        await expect(page.getByTestId("topbar-command-center")).toContainText("Centrum dowodzenia");

        // 3. Switch to English
        // Open language menu
        // The button likely has the current language label "PL" or accessible name "Przełącz język"
        await page.getByRole("button", { name: /Przełącz język|Switch language|Sprache wechseln/i }).click();

        // Select "EN" option details
        // Using text since role composition might be complex with custom rendering
        await expect(page.getByText("English")).toBeVisible();
        await page.getByText("English").click();

        // 4. Verify English content
        // "Command Center" is EN translation
        await expect(page.getByTestId("topbar-command-center")).toContainText("Command Center");

        // 5. Switch to German
        await page.getByRole("button", { name: /Przełącz język|Switch language|Sprache wechseln/i }).click();

        await expect(page.getByText("Deutsch")).toBeVisible();
        await page.getByText("Deutsch").click();

        // 6. Verify German content
        await expect(page.getByTestId("topbar-command-center")).toContainText("Leitstand");

        // 7. Switch back to Polish
        await page.getByRole("button", { name: /Przełącz język|Switch language|Sprache wechseln/i }).click();

        await expect(page.getByText("Polski")).toBeVisible();
        await page.getByText("Polski").click();

        // 8. Verify Polish content again
        await expect(page.getByTestId("topbar-command-center")).toContainText("Centrum dowodzenia");
    });
});
