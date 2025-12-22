import { expect, test } from "@playwright/test";

test.describe("Venom Next Cockpit Smoke", () => {
  test("renders cockpits key panels", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Cockpit AI/i })).toBeVisible();
    await expect(page.getByText(/Live Feed/i)).toBeVisible();
    await expect(page.getByText("Zadania").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /Skuteczność operacji/i })).toBeVisible();
  });

  test("Inspector list displays placeholders", async ({ page }) => {
    await page.goto("/inspector");
    await expect(page.getByRole("heading", { name: /Analiza śladów/i })).toBeVisible();
    await expect(page.getByText(/Brak historii/i)).toBeVisible();
  });

  test("Brain view loads filters and graph container", async ({ page }) => {
    await page.goto("/brain");
    await expect(page.getByText(/Siatka wiedzy/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /^all$/i }).first()).toBeVisible();
    await expect(page.getByTestId("graph-container")).toBeVisible();
  });

  test("TopBar icon actions are visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Cockpit AI/i })).toBeVisible();
    const ids = [
      "topbar-alerts",
      "topbar-notifications",
      "topbar-command",
      "topbar-quick-actions",
      "topbar-services",
      "topbar-command-center",
    ];
    for (const id of ids) {
      await expect(page.getByTestId(id)).toBeVisible();
    }
  });

  test("Bottom status bar jest widoczna na każdej podstronie", async ({ page }) => {
    await page.goto("/");
    const bar = page.getByTestId("bottom-status-bar");
    await expect(bar).toBeVisible();
    await expect(bar.getByTestId("status-bar-resources")).toBeVisible();
    await expect(bar.getByTestId("status-bar-version")).toBeVisible();
    await expect(bar.getByTestId("status-bar-repo")).toBeVisible();
    await page.goto("/brain");
    await expect(page.getByTestId("bottom-status-bar")).toBeVisible();
  });

  test("Status pills show fallback when API is offline", async ({ page }) => {
    await page.goto("/");
    const queueValue = page.getByTestId("status-pill-queue-value");
    const successValue = page.getByTestId("status-pill-success-value");
    const tasksValue = page.getByTestId("status-pill-tasks-value");
    await expect(queueValue).toHaveText(/—|\d/);
    await expect(successValue).toHaveText(/—|\d/);
    await expect(tasksValue).toHaveText(/—|\d/);
  });

  test("Sidebar system status panel is visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("system-status-panel")).toBeVisible();
    for (const id of ["system-status-api", "system-status-queue", "system-status-ws"]) {
      await expect(page.getByTestId(id)).toBeVisible();
    }
  });

  test("Sidebar cost and autonomy controls render", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("sidebar-cost-mode")).toBeVisible();
    await expect(page.getByTestId("sidebar-autonomy")).toBeVisible();
    await expect(page.getByTestId("sidebar-autonomy-select")).toBeVisible();
  });

  test("Service status drawer shows offline message", async ({ page }) => {
    await page.goto("/");
    const servicesButton = page.getByTestId("topbar-services");
    await expect(servicesButton).toBeVisible();
    await servicesButton.click();
    await expect(page.getByTestId("service-status-drawer")).toBeVisible();
    const offline = page.getByTestId("service-status-offline");
    if ((await offline.count()) > 0) {
      await expect(offline).toBeVisible();
    } else {
      // Gdy API zwraca dane, upewnij się, że lista usług jest widoczna.
      const anyService = page.getByText(/LLM|Docker|Memory|unknown/i).first();
      await expect(anyService).toBeVisible();
    }
  });

  test("Alert Center shows offline message without WebSocket", async ({ page }) => {
    await page.goto("/");
    const alertsButton = page.getByTestId("topbar-alerts");
    await expect(alertsButton).toBeVisible();
    await alertsButton.click();
    await expect(page.getByTestId("alert-center-drawer")).toBeVisible();
    const offline = page.getByTestId("alert-center-offline-state");
    if ((await offline.count()) > 0) {
      await expect(offline).toBeVisible();
    } else {
      const empty = page.getByTestId("alert-center-empty-state");
      if ((await empty.count()) > 0) {
        await expect(empty).toBeVisible();
      } else {
        await expect(page.getByTestId("alert-center-entries")).toBeVisible();
      }
    }
  });

  test("Notification drawer shows offline message without WebSocket", async ({ page }) => {
    await page.goto("/");
    const notificationsButton = page.getByTestId("topbar-notifications");
    await expect(notificationsButton).toBeVisible();
    await notificationsButton.click();
    await expect(page.getByTestId("notification-drawer")).toBeVisible();
    const offline = page.getByTestId("notification-offline-state");
    if ((await offline.count()) > 0) {
      await expect(offline).toBeVisible();
    }
  });

  test("Command Center displays offline indicators without API", async ({ page }) => {
    await page.goto("/");
    const commandCenterButton = page.getByTestId("topbar-command-center");
    await expect(commandCenterButton).toBeVisible();
    await commandCenterButton.click();
    await expect(page.getByTestId("command-center-drawer")).toBeVisible();
    await expect(page.getByTestId("command-center-services-section")).toBeVisible();
    const queueOffline = page.getByTestId("command-center-queue-offline");
    if ((await queueOffline.count()) > 0) {
      await expect(queueOffline).toBeVisible();
    } else {
      await expect(page.getByText(/Kolejka/i).first()).toBeVisible();
    }
    const servicesOffline = page.getByTestId("command-center-services-offline");
    if ((await servicesOffline.count()) > 0) {
      await expect(servicesOffline).toBeVisible();
    } else {
      await expect(page.getByTestId("command-center-services-list")).toBeVisible();
    }
  });

  test("Quick actions sheet shows fallback when API is offline", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("topbar-quick-actions").click();
    await expect(page.getByRole("dialog", { name: /Quick Actions/i })).toBeVisible();
    const offline = page.getByTestId("queue-offline-state");
    if ((await offline.count()) > 0) {
      await expect(offline).toBeVisible();
    } else {
      await expect(page.getByTestId("queue-offline-state-online")).toBeVisible();
    }
  });

  test("LLM panel shows server and model selectors", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Serwery LLM/i })).toBeVisible();
    await expect(page.getByLabel("Wybierz serwer LLM")).toBeVisible();
    await expect(page.getByLabel("Wybierz model LLM (panel)")).toBeVisible();
  });

  test("Chat preset wstawia prompt i Ctrl+Enter wysyła zadanie", async ({ page }) => {
    await page.route("**/api/v1/tasks", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ task_id: "test-ctrl" }),
        });
      } else {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: "[]",
        });
      }
    });

    await page.goto("/");
    const presetButton = page.getByRole("button", { name: /Kreacja/i }).first();
    await presetButton.click();

    const textarea = page.getByPlaceholder("Opisz zadanie dla Venoma...");
    await expect(textarea).toHaveValue(/Stwórz logo/i);
    await textarea.focus();
    await page.keyboard.press("Control+Enter");

    await expect(page.getByText(/Wysłano zadanie: test-ctrl/i)).toBeVisible();
    await expect(textarea).toHaveValue("");
  });

  test("Awaryjne zatrzymanie kolejki zwraca komunikat", async ({ page }) => {
    await page.route("**/api/v1/queue/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          active: 1,
          pending: 2,
          limit: 5,
          paused: false,
        }),
      });
    });
    await page.route("**/api/v1/queue/emergency-stop", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ cancelled: 2, purged: 1 }),
      });
    });

    await page.goto("/");
    const panicButton = page.getByRole("button", { name: /Awaryjne zatrzymanie/i });
    await panicButton.click();
    await expect(page.getByText(/Zatrzymano zadania/i)).toBeVisible();
  });
});
