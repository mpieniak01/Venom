import { test, expect } from "@playwright/test";

test.describe("Internationalization (i18n)", () => {
    test.use({ viewport: { width: 1600, height: 1080 } });

    test("should switch languages and update UI content (Topbar + Sidebar)", async ({ page }) => {
        // 1. Start at home page
        await page.goto("/");

        // Wait for hydration/rendering
        await expect(page.getByTestId("topbar-command-center")).toBeVisible();

        // 2. Check default language (PL)
        // Topbar
        await expect(page.getByTestId("topbar-command-center")).toContainText("Centrum dowodzenia");

        // Sidebar
        // Debug: Check if sidebar is collapsed by checking width or class
        // But simply targeting the link text should work if visible.
        // We force open it just in case.
        const toggle = page.getByTestId("sidebar-toggle");
        if (await toggle.isVisible()) {
            // If we see the toggle, we ensure it is in expanded state?
            // Actually, let's just assert the text is there, even if hidden, to confirm translation first?
            // No, user wants verification of "UI content".
            // We use 'active' link logic
        }

        // Try using locator with href which is stable
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
