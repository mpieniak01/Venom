import { expect, Page, Route, test } from "@playwright/test";

const emptyJson = JSON.stringify([]);

const registerBaseRoutes = async (page: Page) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("venom-session-id", "session-test");
    window.localStorage.setItem("venom-backend-boot-id", "boot-test");
    window.localStorage.setItem("venom-next-build-id", "test-build");
  });

  await page.route("**/api/v1/system/status", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ boot_id: "boot-test" }),
    });
  });
  await page.route("**/api/v1/system/services", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ services: [] }),
    });
  });
  await page.route("**/api/v1/metrics/tokens", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });
  await page.route("**/api/v1/models/usage", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ usage: {} }),
    });
  });
  await page.route("**/api/v1/queue/status", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ active: 0, queued: 0 }),
    });
  });
  await page.route("**/api/v1/learning/logs", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: emptyJson,
    });
  });
  await page.route("**/api/v1/feedback/logs", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: emptyJson,
    });
  });
  await page.route("**/api/v1/hidden-prompts/active**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: emptyJson,
    });
  });
  await page.route("**/api/v1/hidden-prompts**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: emptyJson,
    });
  });
  await page.route("**/api/v1/git/status", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "clean" }),
    });
  });
  await page.route("**/api/v1/models/active", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });
  await page.route("**/api/v1/models", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ providers: {} }),
    });
  });
};

type MockPayload = {
  event: string;
  data: Record<string, unknown>;
};

const installMockEventSource = async (page: Page, payloads: MockPayload[]) => {
  await page.addInitScript(
    ({ payloads }) => {
      const encodePayloads = (items: MockPayload[]) =>
        items.map((payload) => ({
          event: payload.event,
          data: JSON.stringify(payload.data),
        }));

      const emitPayload = (
        listeners: Record<string, Array<(event: MessageEvent) => void>>,
        payload: { event: string; data: string },
      ) => {
        const event = new MessageEvent(payload.event, { data: payload.data });
        for (const handler of listeners[payload.event] || []) {
          handler(event);
        }
      };

      const schedulePayloads = (
        listeners: Record<string, Array<(event: MessageEvent) => void>>,
        encoded: Array<{ event: string; data: string }>,
      ) => {
        for (let index = 0; index < encoded.length; index += 1) {
          setTimeout(() => emitPayload(listeners, encoded[index]), 150 * (index + 1));
        }
      };

      const encodedPayloads = encodePayloads(payloads);

      class MockEventSource {
        url: string;
        onopen: ((event: Event) => void) | null = null;
        onerror: ((event: Event) => void) | null = null;
        private listeners: Record<string, Array<(event: MessageEvent) => void>> = {};

        constructor(url: string) {
          this.url = url;
          setTimeout(() => {
            this.onopen?.(new Event("open"));
            schedulePayloads(this.listeners, encodedPayloads);
          }, 50);
        }

        addEventListener(event: string, handler: (event: MessageEvent) => void) {
          this.listeners[event] = this.listeners[event] || [];
          this.listeners[event].push(handler);
        }

        removeEventListener(event: string, handler: (event: MessageEvent) => void) {
          if (this.listeners[event]) {
            this.listeners[event] = this.listeners[event].filter((item) => item !== handler);
          }
        }

        close() {
          this.listeners = {};
        }
      }

      // @ts-expect-error - mock EventSource in test runtime
      window.EventSource = MockEventSource;
    },
    { payloads },
  );
};

test.describe("Chat context icons", () => {
  test.beforeEach(async ({ page }) => {
    await registerBaseRoutes(page);
    await page.addInitScript(() => {
      window.localStorage.setItem("venom-language", "pl");
    });
  });

  test("shows 🎓 and 🧠 when context_used has lessons and memory_entries", async ({ page }) => {
    await installMockEventSource(page, [
      {
        event: "task_update",
        data: {
          task_id: "icon-test-123",
          status: "PROCESSING",
          logs: ["Start"],
        },
      },
      {
        event: "task_finished",
        data: {
          task_id: "icon-test-123",
          status: "COMPLETED",
          result: "SSE wynik odpowiedzi",
          context_used: {
            lessons: ["l1", "l2"],
            memory_entries: ["m1"],
          },
        },
      },
    ]);

    await page.route("**/api/v1/history/requests?limit=6", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
    });

    await page.route("**/api/v1/tasks", async (route: Route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ task_id: "icon-test-123" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
    });

    await page.goto("/");
    await page.waitForFunction(
      () => document.documentElement.dataset.hydrated === "true",
      undefined,
      { timeout: 10000 },
    );
    const chatHistory = page.getByTestId("cockpit-chat-history");
    await chatHistory.scrollIntoViewIfNeeded();
    await page.getByTestId("cockpit-prompt-input").fill("Sprawdz ikony");
    await page.getByTestId("cockpit-send-button").click();

    const history = page.getByTestId("cockpit-chat-history");
    await expect(history.getByText(/🎓\s*2/)).toBeVisible();
    await expect(history.getByText(/🧠\s*1/)).toBeVisible();
  });

  test("does not show 🎓/🧠 when context_used is missing", async ({ page }) => {
    await installMockEventSource(page, [
      {
        event: "task_update",
        data: {
          task_id: "icon-test-456",
          status: "PROCESSING",
          logs: ["Start"],
        },
      },
      {
        event: "task_finished",
        data: {
          task_id: "icon-test-456",
          status: "COMPLETED",
          result: "SSE wynik bez ikon",
        },
      },
    ]);

    await page.route("**/api/v1/history/requests?limit=6", async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
    });

    await page.route("**/api/v1/tasks", async (route: Route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ task_id: "icon-test-456" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
    });

    await page.goto("/");
    await page.waitForFunction(
      () => document.documentElement.dataset.hydrated === "true",
      undefined,
      { timeout: 10000 },
    );
    const chatHistory = page.getByTestId("cockpit-chat-history");
    await chatHistory.scrollIntoViewIfNeeded();
    await page.getByTestId("cockpit-prompt-input").fill("Sprawdz brak ikon");
    await page.getByTestId("cockpit-send-button").click();

    await expect(chatHistory.getByText(/🎓/)).toHaveCount(0);
    await expect(chatHistory.getByText(/🧠/)).toHaveCount(0);
  });
});
