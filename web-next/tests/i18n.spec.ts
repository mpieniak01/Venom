import { test, expect } from "@playwright/test";

test.describe("Internationalization (i18n)", () => {
    test.use({ viewport: { width: 1600, height: 1080 } });

    test("should switch languages and update UI content (Topbar + Sidebar)", async ({ page }) => {
        // 1. Start at home page
        await page.goto("/");

        // Wait for hydration/rendering
        await expect(page.getByTestId("topbar-command-center")).toBeVisible();

        // 2. Ensure we wait for hydration/readiness by checking for any valid topbar text
        const topbar = page.getByTestId("topbar-command-center");
        await expect(topbar).not.toHaveText(""); // Wait until it has any text

        const topbarText = await topbar.textContent();
        if (topbarText?.includes("Command Center")) {
            // Switch to PL
            await page.getByRole("button", { name: /Switch language/i }).click();
            await page.getByText("Polski").click();
        }

        // Check default/current language (PL)
        // Topbar
        await expect(page.getByTestId("topbar-command-center")).toContainText("Centrum dowodzenia");

        // Sidebar
        const calendarLink = page.locator('a[href="/calendar"]');
        await expect(calendarLink).toBeVisible();
        await expect(calendarLink).toHaveAttribute("aria-label", "Kalendarz");

        // 3. Switch to English
        // Open language menu
        await page.getByRole("button", { name: /Przełącz język|Switch language|Sprache wechseln/i }).click();

        // Select "EN" option details
        await expect(page.getByText("English")).toBeVisible();
        await page.getByText("English").click();

        // 4. Verify English content
        // Topbar
        await expect(page.getByTestId("topbar-command-center")).toContainText("Command Center");
        // Sidebar
        await expect(page.locator('a[href="/calendar"]')).toHaveAttribute("aria-label", "Calendar");

        // 5. Switch to German
        await page.getByRole("button", { name: /Przełącz język|Switch language|Sprache wechseln/i }).click();

        await expect(page.getByText("Deutsch")).toBeVisible();
        await page.getByText("Deutsch").click();

        // 6. Verify German content
        // Topbar
        await expect(page.getByTestId("topbar-command-center")).toContainText("Leitstand");
        // Sidebar
        await expect(page.locator('a[href="/calendar"]')).toHaveAttribute("aria-label", "Kalender");

        // 7. Switch back to Polish
        await page.getByRole("button", { name: /Przełącz język|Switch language|Sprache wechseln/i }).click();

        await expect(page.getByText("Polski")).toBeVisible();
        await page.getByText("Polski").click();

        // 8. Verify Polish content again
        await expect(page.getByTestId("topbar-command-center")).toContainText("Centrum dowodzenia");
        await expect(page.locator('a[href="/calendar"]')).toHaveAttribute("aria-label", "Kalendarz");
    });
});
