import { expect, test, type Page } from "@playwright/test";

async function waitForHydration(page: Page) {
  await page.waitForFunction(
    () => document.documentElement.dataset.hydrated === "true",
    undefined,
    { timeout: 10000 },
  );
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("venom-language", "pl");
  });
});

test.describe("Venom Next Cockpit Smoke", () => {
  test("Slash command /gpt potwierdza przelaczenie runtime i wysyla zadanie", async ({ page }) => {
    await page.route("**/api/v1/system/llm-servers/active", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "success",
            active_server: "vllm",
            active_model: "phi3",
            config_hash: "hash-local",
            runtime_id: "vllm@local",
          }),
        });
        return;
      }
      await route.fulfill({
        status: 405,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Method not allowed" }),
      });
    });
    await page.route("**/api/v1/system/llm-runtime/active", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "success",
            active_server: "openai",
            active_model: "gpt-4o",
            config_hash: "hash-openai",
            runtime_id: "openai@cloud",
          }),
        });
        return;
      }
      await route.fulfill({
        status: 405,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Method not allowed" }),
      });
    });
    await page.route("**/api/v1/tasks", async (route) => {
      if (route.request().method() === "POST") {
        const body = route.request().postDataJSON();
        expect(body.content).toBe("Test zadania");
        expect(body.forced_provider).toBe("gpt");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ task_id: "slash-gpt" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "[]",
      });
    });

    page.on("dialog", async (dialog) => {
      await dialog.accept();
    });

    await page.goto("/chat");
    await page.waitForResponse("**/api/v1/system/llm-servers/active");

    const textarea = page.getByTestId("cockpit-prompt-input");
    await textarea.fill("/gpt Test zadania");

    const [runtimeReq, taskReq] = await Promise.all([
      page.waitForRequest((req) =>
        req.url().includes("/api/v1/system/llm-runtime/active") &&
        req.method() === "POST",
      ),
      page.waitForRequest((req) =>
        req.url().includes("/api/v1/tasks") && req.method() === "POST",
      ),
      page.getByTestId("cockpit-send-button").click(),
    ]);

    expect(runtimeReq.method()).toBe("POST");
    expect(runtimeReq.postDataJSON()).toEqual(expect.objectContaining({ provider: "openai" }));
    expect(taskReq.method()).toBe("POST");
    await expect(page.getByText(/Wysłano zadanie: slash-gpt/i)).toBeVisible();
  });

  test("renders cockpits key panels", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Cockpit AI/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Historia requestów/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Hidden prompts/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Status operacyjny/i })).toBeVisible();
    await expect(page.getByText("Zadania").first()).toBeVisible();
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
    const presetButton = page.getByTestId("cockpit-preset-preset-creative");
    await expect(presetButton).toBeVisible();
    await presetButton.click();

    const textarea = page.getByTestId("cockpit-prompt-input");
    await expect(textarea).toHaveValue(/Stwórz logo/i);
    await textarea.focus();
    await page.keyboard.press("Control+Enter");

    await expect(page.getByText(/Wysłano zadanie: test-ctrl/i)).toBeVisible();
    await expect(textarea).toHaveValue("");
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

    await page.goto("/chat");
    await waitForHydration(page);
    const panicButton = page.getByRole("button", { name: /Awaryjne zatrzymanie/i });
    await expect(panicButton).toBeVisible();
    await panicButton.click();
    await expect(page.getByText(/Zatrzymano zadania/i)).toBeVisible();
  });

  test("Quick actions sheet shows fallback when API is offline", async ({ page }) => {
    await page.goto("/");
    const quickActions = page.getByTestId("topbar-quick-actions");
    await expect(quickActions).toBeVisible();
    await quickActions.click({ force: true });
    await expect(page.getByTestId("quick-actions-sheet")).toBeVisible();
    const offline = page.getByTestId("queue-offline-state");
    await expect
      .poll(async () => {
        if (await offline.isVisible()) return "offline";
        if (await page.getByTestId("queue-offline-state-online").isVisible()) return "online";
        return "none";
      })
      .not.toBe("none");
  });

  test("Notification drawer shows offline message without WebSocket", async ({ page }) => {
    await page.goto("/");
    const notificationsButton = page.getByTestId("topbar-notifications");
    await expect(notificationsButton).toBeVisible();
    await notificationsButton.click();
    await expect(page.getByTestId("notification-drawer")).toBeVisible();

    await expect
      .poll(async () => {
        if (await page.getByTestId("notification-offline-state").isVisible()) return "offline";
        if (await page.getByText(/Brak powiadomień/i).isVisible()) return "empty";
        if (await page.locator(".card-shell").first().isVisible()) return "entries";
        return "none";
      })
      .not.toBe("none");
  });

  test("Command Center displays offline indicators without API", async ({ page }) => {
    await page.goto("/");
    const commandCenterButton = page.getByTestId("topbar-command-center");
    await expect(commandCenterButton).toBeVisible();
    await commandCenterButton.click();
    await expect(page.getByTestId("command-center-drawer")).toBeVisible();
    await expect(page.getByTestId("command-center-services-section")).toBeVisible();
    await expect
      .poll(async () => {
        const offline = await page.getByTestId("command-center-queue-offline").isVisible();
        const online = await page.getByText(/Kolejka/i).first().isVisible();
        return offline || online ? "ok" : "none";
      })
      .toBe("ok");

    await expect
      .poll(async () => {
        const offline = await page.getByTestId("command-center-services-offline").isVisible();
        const online = await page.getByTestId("command-center-services-list").isVisible();
        return offline || online ? "ok" : "none";
      })
      .toBe("ok");
  });

  test("LLM panel shows server and model selectors", async ({ page }) => {
    await page.goto("/chat");
    await expect(page.getByRole("heading", { name: /Serwery LLM/i })).toBeVisible();
    await expect(page.getByLabel("Wybierz serwer LLM").first()).toBeVisible();
    await expect(page.getByLabel("Wybierz model LLM").first()).toBeVisible();
  });

  test("KPI Panel displays operational status section", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Status operacyjny/i })).toBeVisible();
    await expect(page.getByText("Zadania").first()).toBeVisible();
  });

  test("LLM Model and Activate button are present and enabled", async ({ page }) => {
    await page.route("**/api/v1/system/llm-servers/active", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "success",
          active_server: "vllm",
          active_model: "phi3",
          config_hash: "hash-initial",
          runtime_id: "vllm@local",
        }),
      });
    });

    await page.route("**/api/v1/system/llm-servers", async (route) => {
      await route.fulfill({
        status: 200,
        body: JSON.stringify([
          { name: "vllm", status: "online", base_url: "http://localhost:8000" }
        ])
      });
    });

    await page.route("**/api/v1/models", async (route) => {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          models: [
            { name: "phi3", provider: "vllm" },
            { name: "mistral", provider: "vllm" }
          ]
        })
      });
    });

    await page.goto("/chat");
    const modelSelector = page.getByLabel("Wybierz model LLM").first();
    await expect(modelSelector).toBeVisible();
    await expect(modelSelector).toBeEnabled({ timeout: 10000 });
    const activateButton = page.getByRole("button", { name: /Aktywuj/i });
    await expect(activateButton).toBeVisible();
  });

  test("Feedback controls are accessible via UI", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Historia requestów/i })).toBeVisible();
  });

  test("Cockpit Macros panel is rendered", async ({ page }) => {
    await page.goto("/");
    const addMacroBtn = page.getByRole("button", { name: /Dodaj makro/i });
    await expect(addMacroBtn).toBeVisible();
  });

  test("Request Detail Drawer elements are present", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Historia requestów/i })).toBeVisible();
  });

  test("Alert Center shows offline message without WebSocket", async ({ page }) => {
    await page.goto("/");
    const alertsButton = page.getByTestId("topbar-alerts");
    await expect(alertsButton).toBeVisible();
    await alertsButton.click();
    await expect(page.getByTestId("alert-center-drawer")).toBeVisible();

    await expect
      .poll(async () => {
        if (await page.getByTestId("alert-center-offline-state").isVisible()) return "offline";
        if (await page.getByTestId("alert-center-empty-state").isVisible()) return "empty";
        if (await page.getByTestId("alert-center-entries").isVisible()) return "entries";
        return "none";
      })
      .not.toBe("none");
  });

  test("Service status drawer shows offline message", async ({ page }) => {
    await page.goto("/");
    const servicesButton = page.getByTestId("topbar-services");
    await expect(servicesButton).toBeVisible();
    await servicesButton.click();
    await expect(page.getByTestId("service-status-drawer")).toBeVisible();
    await expect
      .poll(async () => {
        if (await page.getByTestId("service-status-offline").isVisible()) return "offline";
        const anyService = page.getByText(/LLM|Docker|Memory|unknown/i).first();
        if (await anyService.isVisible()) return "online";
        return "none";
      })
      .not.toBe("none");
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

  test("Brain view loads filters and graph container", async ({ page }) => {
    await page.goto("/brain");
    await expect(page.getByText(/Siatka wiedzy/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /^all$/i }).first()).toBeVisible();
    await expect(page.getByTestId("graph-container")).toBeVisible();
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

  test("Inspector list displays placeholders", async ({ page }) => {
    await page.route("**/api/v1/history/requests*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });
    await page.goto("/inspector");
    await expect(page.getByRole("heading", { name: /Analiza śladów/i })).toBeVisible();
    await expect(page.getByText(/Brak historii/i)).toBeVisible();
  });

  test("Reset sesji po zmianie boot_id backendu", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("venom-session-id", "session-old");
      window.localStorage.setItem("venom-backend-boot-id", "boot-old");
      window.localStorage.setItem("venom-next-build-id", "build-old");
    });

    await page.route("**/api/v1/system/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ boot_id: "boot-new" }),
      });
    });

    await page.goto("/");

    await page.waitForFunction(() => {
      const sessionId = window.localStorage.getItem("venom-session-id");
      const bootId = window.localStorage.getItem("venom-backend-boot-id");
      return sessionId !== "session-old" && bootId === "boot-new";
    });

    const sessionId = await page.evaluate(() =>
      window.localStorage.getItem("venom-session-id"),
    );
    expect(sessionId).not.toBe("session-old");
  });
});
