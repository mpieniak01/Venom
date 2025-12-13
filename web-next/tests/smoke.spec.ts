import { expect, test } from "@playwright/test";

const BASE_URL = process.env.BASE_URL || "http://localhost:3000";

test.describe("Venom Next Cockpit Smoke", () => {
  test("renders cockpits key panels", async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await expect(page.getByRole("heading", { name: /Cockpit/i })).toBeVisible();
    await expect(page.getByText("Nowy frontend w Next.js")).toBeVisible();

    // Metrics cards
    await expect(page.getByText("Zadania")).toBeVisible();
    await expect(page.getByText("Success rate")).toBeVisible();
  });

  test("Flow list displays placeholders", async ({ page }) => {
    await page.goto(`${BASE_URL}/flow`);
    await expect(page.getByRole("heading", { name: /Flow Inspector/i })).toBeVisible();
    await expect(page.getByText(/Brak historii/i)).toBeVisible();
  });

  test("Brain view loads filters and graph container", async ({ page }) => {
    await page.goto(`${BASE_URL}/brain`);
    await expect(page.getByText(/Brain \/ Knowledge Graph/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /all/i })).toBeVisible();
    await expect(page.locator("#cy").first()).toBeVisible();
  });
});
