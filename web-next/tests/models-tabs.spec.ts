import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("venom-language", "pl");
  });
});

test.describe("Models Page Tabs", () => {
  test("switches between News and Models tabs and displays correct sections", async ({ page }) => {
    // Mock API endpoints that models page might need
    await page.route("**/api/v1/models**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ models: [] }),
      });
    });

    await page.route("**/api/v1/system/llm-servers/active", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "success",
          active_server: "vllm",
          active_model: "phi3",
        }),
      });
    });

    await page.route("**/api/v1/system/llm-servers", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    // Navigate to models page
    await page.goto("/models");

    // Verify News tab is active by default
    const newsTab = page.getByRole("button", { name: /Nowości/i });
    const modelsTab = page.getByRole("button", { name: /^Modele$/i });

    await expect(newsTab).toBeVisible();
    await expect(modelsTab).toBeVisible();

    // Verify News tab sections are visible
    await expect(page.getByText(/NEWS/i).first()).toBeVisible();
    await expect(page.getByText(/PAPERS/i).first()).toBeVisible();
    await expect(page.getByText(/POLECANE/i).first()).toBeVisible();
    await expect(page.getByText(/KATALOG/i).first()).toBeVisible();

    // Verify Models tab sections are NOT visible initially
    await expect(page.getByText(/Runtime Control/i).or(page.getByText(/Sterowanie Runtime/i))).not.toBeVisible();
    await expect(page.getByText(/FIND MODEL/i).or(page.getByText(/ZNAJDŹ MODEL/i))).not.toBeVisible();

    // Click on Models tab
    await modelsTab.click();

    // Verify Models tab sections are now visible
    await expect(page.getByText(/Runtime Control/i).or(page.getByText(/Sterowanie Runtime/i))).toBeVisible();
    await expect(page.getByText(/FIND MODEL/i).or(page.getByText(/ZNAJDŹ MODEL/i))).toBeVisible();
    await expect(page.getByText(/ZAINSTALOWANE/i).or(page.getByText(/INSTALLED/i))).toBeVisible();
    await expect(page.getByText(/OPERACJE/i).or(page.getByText(/OPERATIONS/i))).toBeVisible();

    // Verify News sections are NOT visible anymore
    await expect(page.getByText(/NEWS/i).first()).not.toBeVisible();

    // Switch back to News tab
    await newsTab.click();

    // Verify News sections are visible again
    await expect(page.getByText(/NEWS/i).first()).toBeVisible();
    await expect(page.getByText(/POLECANE/i).first()).toBeVisible();

    // Verify Models sections are hidden again
    await expect(page.getByText(/Runtime Control/i).or(page.getByText(/Sterowanie Runtime/i))).not.toBeVisible();
  });

  test("POLECANE and KATALOG sections have distinct descriptions", async ({ page }) => {
    await page.route("**/api/v1/models**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ models: [] }),
      });
    });

    await page.goto("/models");

    // Wait for the page to load
    await expect(page.getByText(/POLECANE/i).first()).toBeVisible();
    await expect(page.getByText(/KATALOG/i).first()).toBeVisible();

    // Get the parent containers of POLECANE and KATALOG sections
    const recommendedSection = page.locator("text=POLECANE").first().locator("..");
    const catalogSection = page.locator("text=KATALOG").first().locator("..");

    // Verify that both sections have descriptions (italic text)
    await expect(recommendedSection.locator("p.italic")).toBeVisible();
    await expect(catalogSection.locator("p.italic")).toBeVisible();

    // Verify descriptions are different by checking they contain different text
    const recommendedDesc = await recommendedSection.locator("p.italic").textContent();
    const catalogDesc = await catalogSection.locator("p.italic").textContent();

    expect(recommendedDesc).toBeTruthy();
    expect(catalogDesc).toBeTruthy();
    expect(recommendedDesc).not.toBe(catalogDesc);
  });

  test("maintains tab state and all operational actions are accessible", async ({ page }) => {
    await page.route("**/api/v1/models**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          models: [
            { name: "test-model", provider: "ollama", size: 1000000 }
          ]
        }),
      });
    });

    await page.route("**/api/v1/system/llm-servers/active", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "success",
          active_server: "vllm",
          active_model: "phi3",
        }),
      });
    });

    await page.route("**/api/v1/system/llm-servers", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          { name: "vllm", status: "online" }
        ]),
      });
    });

    await page.goto("/models");

    // Switch to Models tab
    await page.getByRole("button", { name: /^Modele$/i }).click();

    // Verify operational sections are accessible
    await expect(page.getByText(/Runtime Control/i).or(page.getByText(/Sterowanie Runtime/i))).toBeVisible();

    // Verify activate button exists (operational action preserved)
    await expect(page.getByRole("button", { name: /Aktywuj/i })).toBeVisible();

    // Verify search functionality exists
    await expect(page.getByPlaceholder(/Model name/i).or(page.getByPlaceholder(/Nazwa modelu/i))).toBeVisible();

    // Verify installed models section exists
    await expect(page.getByText(/ZAINSTALOWANE/i).or(page.getByText(/INSTALLED/i))).toBeVisible();
  });
});
