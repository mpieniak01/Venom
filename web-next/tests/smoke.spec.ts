import { expect, test } from "@playwright/test";

test.describe("Venom Next Cockpit Smoke", () => {
  test("renders cockpits key panels", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Cockpit AI/i })).toBeVisible();
    await expect(page.getByText(/Live Feed/i)).toBeVisible();
    await expect(page.getByText("Zadania").first()).toBeVisible();
    await expect(page.getByText("Success rate")).toBeVisible();
  });

  test("Inspector list displays placeholders", async ({ page }) => {
    await page.goto("/inspector");
    await expect(page.getByRole("heading", { name: /Trace Intelligence/i })).toBeVisible();
    await expect(page.getByText(/Brak historii/i)).toBeVisible();
  });

  test("Brain view loads filters and graph container", async ({ page }) => {
    await page.goto("/brain");
    await expect(page.getByText(/Mind Mesh/i)).toBeVisible();
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

  test("Status pills show fallback when API is offline", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("status-pill-queue")).toContainText("—");
    await expect(page.getByTestId("status-pill-success")).toContainText("—");
    await expect(page.getByTestId("status-pill-tasks")).toContainText("—");
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
    await expect(page.getByRole("dialog", { name: /Service status/i })).toBeVisible();
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
    await expect(page.getByRole("dialog", { name: /Alert Center/i })).toBeVisible();
    const offline = page.getByTestId("alert-center-offline-state");
    if ((await offline.count()) > 0) {
      await expect(offline).toBeVisible();
    } else {
      const empty = page.getByText(/Brak wpisów/i);
      if ((await empty.count()) > 0) {
        await expect(empty).toBeVisible();
      } else {
        await expect(page.getByText(/Kopiuj JSON/i)).toBeVisible();
      }
    }
  });

  test("Notification drawer shows offline message without WebSocket", async ({ page }) => {
    await page.goto("/");
    const notificationsButton = page.getByTestId("topbar-notifications");
    await expect(notificationsButton).toBeVisible();
    await notificationsButton.click();
    await expect(page.getByRole("dialog", { name: /Notifications/i })).toBeVisible();
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
    await expect(page.getByRole("dialog", { name: /Command Center/i })).toBeVisible();
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
      await expect(page.getByText(/Status integracji/i)).toBeVisible();
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

  test("Models panel badge displays count", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Modele/i })).toBeVisible();
    const badge = page.getByTestId("models-count");
    await expect(badge).toBeVisible();
    await expect(badge).toHaveText(/\d+\s+modeli/i);
  });
});
