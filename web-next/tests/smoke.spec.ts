import { expect, test } from "@playwright/test";

const BASE_URL = process.env.BASE_URL || "http://localhost:3000";

test.describe("Venom Next Cockpit Smoke", () => {
  test("renders cockpits key panels", async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await expect(page.getByRole("heading", { name: /Cockpit AI/i })).toBeVisible();
    await expect(page.getByText(/Live Feed/i)).toBeVisible();
    await expect(page.getByText("Zadania").first()).toBeVisible();
    await expect(page.getByText("Success rate")).toBeVisible();
  });

  test("Inspector list displays placeholders", async ({ page }) => {
    await page.goto(`${BASE_URL}/inspector`);
    await expect(page.getByRole("heading", { name: /Trace Intelligence/i })).toBeVisible();
    await expect(page.getByText(/Brak historii/i)).toBeVisible();
  });

  test("Brain view loads filters and graph container", async ({ page }) => {
    await page.goto(`${BASE_URL}/brain`);
    await expect(page.getByText(/Mind Mesh/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /^all$/i }).first()).toBeVisible();
    await expect(page.getByTestId("graph-container")).toBeVisible();
  });
});
