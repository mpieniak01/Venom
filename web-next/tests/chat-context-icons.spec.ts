import { expect, test } from "@playwright/test";

const emptyJson = JSON.stringify([]);

const registerBaseRoutes = async (page: any) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("venom-session-id", "session-test");
    window.localStorage.setItem("venom-backend-boot-id", "boot-test");
    window.localStorage.setItem("venom-next-build-id", "test-build");
  });

  await page.route("**/api/v1/system/status", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ boot_id: "boot-test" }),
    });
  });
  await page.route("**/api/v1/system/services", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ services: [] }),
    });
  });
  await page.route("**/api/v1/metrics/tokens", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });
  await page.route("**/api/v1/models/usage", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ usage: {} }),
    });
  });
  await page.route("**/api/v1/queue/status", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ active: 0, queued: 0 }),
    });
  });
  await page.route("**/api/v1/learning/logs", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: emptyJson,
    });
  });
  await page.route("**/api/v1/feedback/logs", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: emptyJson,
    });
  });
  await page.route("**/api/v1/hidden-prompts/active**", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: emptyJson,
    });
  });
  await page.route("**/api/v1/hidden-prompts**", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: emptyJson,
    });
  });
  await page.route("**/api/v1/git/status", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "clean" }),
    });
  });
  await page.route("**/api/v1/models/active", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });
  await page.route("**/api/v1/models", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ providers: {} }),
    });
  });
};

test.describe("Chat context icons", () => {
  test.beforeEach(async ({ page }) => {
    await registerBaseRoutes(page);
  });

  test("shows 🎓 and 🧠 when context_used has lessons and memory_entries", async ({ page }) => {
    await page.addInitScript(() => {
      class MockEventSource {
        url: string;
        onopen: ((event: Event) => void) | null = null;
        onerror: ((event: Event) => void) | null = null;
        private listeners: Record<string, Array<(event: MessageEvent) => void>> = {};

        constructor(url: string) {
          this.url = url;
          setTimeout(() => {
            this.onopen?.(new Event("open"));
            const payloads = [
              {
                event: "task_update",
                data: JSON.stringify({
                  task_id: "icon-test-123",
                  status: "PROCESSING",
                  logs: ["Start"],
                }),
              },
              {
                event: "task_finished",
                data: JSON.stringify({
                  task_id: "icon-test-123",
                  status: "COMPLETED",
                  result: "SSE wynik odpowiedzi",
                  context_used: {
                    lessons: ["l1", "l2"],
                    memory_entries: ["m1"],
                  },
                }),
              },
            ];
            payloads.forEach((payload, index) => {
              setTimeout(() => {
                const event = new MessageEvent(payload.event, { data: payload.data });
                (this.listeners[payload.event] || []).forEach((handler) => handler(event));
              }, 150 * (index + 1));
            });
          }, 50);
        }

        addEventListener(event: string, handler: (event: MessageEvent) => void) {
          this.listeners[event] = this.listeners[event] || [];
          this.listeners[event].push(handler);
        }

        removeEventListener(event: string, handler: (event: MessageEvent) => void) {
          if (this.listeners[event]) {
            this.listeners[event] = this.listeners[event].filter(h => h !== handler);
          }
        }

        close() {
          this.listeners = {};
        }
      }

      // @ts-expect-error - mock EventSource in test runtime
      window.EventSource = MockEventSource;
    });

    await page.route("**/api/v1/history/requests?limit=6", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
    });

    await page.route("**/api/v1/tasks", async (route) => {
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
    const chatHistory = page.getByTestId("cockpit-chat-history");
    await chatHistory.scrollIntoViewIfNeeded();
    await page.getByTestId("cockpit-prompt-input").fill("Sprawdz ikony");
    await page.getByTestId("cockpit-send-button").click();

    const history = page.getByTestId("cockpit-chat-history");
    await expect(history.getByText(/🎓\s*2/)).toBeVisible();
    await expect(history.getByText(/🧠\s*1/)).toBeVisible();
  });

  test("does not show 🎓/🧠 when context_used is missing", async ({ page }) => {
    await page.addInitScript(() => {
      class MockEventSource {
        url: string;
        onopen: ((event: Event) => void) | null = null;
        onerror: ((event: Event) => void) | null = null;
        private listeners: Record<string, Array<(event: MessageEvent) => void>> = {};

        constructor(url: string) {
          this.url = url;
          setTimeout(() => {
            this.onopen?.(new Event("open"));
            const payloads = [
              {
                event: "task_update",
                data: JSON.stringify({
                  task_id: "icon-test-456",
                  status: "PROCESSING",
                  logs: ["Start"],
                }),
              },
              {
                event: "task_finished",
                data: JSON.stringify({
                  task_id: "icon-test-456",
                  status: "COMPLETED",
                  result: "SSE wynik bez ikon",
                }),
              },
            ];
            payloads.forEach((payload, index) => {
              setTimeout(() => {
                const event = new MessageEvent(payload.event, { data: payload.data });
                (this.listeners[payload.event] || []).forEach((handler) => handler(event));
              }, 150 * (index + 1));
            });
          }, 50);
        }

        addEventListener(event: string, handler: (event: MessageEvent) => void) {
          this.listeners[event] = this.listeners[event] || [];
          this.listeners[event].push(handler);
        }

        removeEventListener(event: string, handler: (event: MessageEvent) => void) {
          if (this.listeners[event]) {
            this.listeners[event] = this.listeners[event].filter(h => h !== handler);
          }
        }

        close() {
          this.listeners = {};
        }
      }

      // @ts-expect-error - mock EventSource in test runtime
      window.EventSource = MockEventSource;
    });

    await page.route("**/api/v1/history/requests?limit=6", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
    });

    await page.route("**/api/v1/tasks", async (route) => {
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
    const chatHistory = page.getByTestId("cockpit-chat-history");
    await chatHistory.scrollIntoViewIfNeeded();
    await page.getByTestId("cockpit-prompt-input").fill("Sprawdz brak ikon");
    await page.getByTestId("cockpit-send-button").click();

    await expect(chatHistory.getByText(/🎓/)).toHaveCount(0);
    await expect(chatHistory.getByText(/🧠/)).toHaveCount(0);
  });
});
