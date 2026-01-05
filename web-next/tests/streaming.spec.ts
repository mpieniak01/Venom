import { expect, test } from "@playwright/test";

const emptyJson = JSON.stringify([]);

test.describe("Cockpit streaming SSE", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("venom-session-id", "session-test");
      window.localStorage.setItem("venom-backend-boot-id", "boot-test");
      window.localStorage.setItem("venom-next-build-id", "test-build");
    });
    await page.route("**/api/v1/system/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ boot_id: "boot-test" }),
      });
    });
    await page.route("**/api/v1/system/services", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ services: [] }),
      });
    });
    await page.route("**/api/v1/metrics/tokens", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });
    await page.route("**/api/v1/queue/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ active: 0, queued: 0 }),
      });
    });
    await page.route("**/api/v1/learning/logs", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
    });
    await page.route("**/api/v1/feedback/logs", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
    });
    await page.route("**/api/v1/hidden-prompts/active**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
    });
    await page.route("**/api/v1/hidden-prompts**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
    });
    await page.route("**/api/v1/git/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "clean" }),
      });
    });
    await page.route("**/api/v1/models/active", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });
    await page.route("**/api/v1/models", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ providers: {} }),
      });
    });
  });

  test("aktualizuje bąbel rozmowy po zdarzeniach SSE", async ({ page }) => {
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
                  task_id: "sse-test-123",
                  status: "PROCESSING",
                  logs: ["Rozpoczynam streaming odpowiedzi"],
                }),
              },
              {
                event: "task_finished",
                data: JSON.stringify({
                  task_id: "sse-test-123",
                  status: "COMPLETED",
                  result: "SSE wynik odpowiedzi",
                }),
              },
            ];
            payloads.forEach((payload, index) => {
              setTimeout(() => {
                (window as any).__taskStreamEvents = [
                  ...((window as any).__taskStreamEvents ?? []),
                  { event: payload.event, ...(JSON.parse(payload.data) || {}) },
                ].slice(-25);
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
          body: JSON.stringify({ task_id: "sse-test-123" }),
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
    const textarea = page.getByPlaceholder("Opisz zadanie dla Venoma...");
    await textarea.fill("Przetestuj strumień SSE");
    await page.getByRole("button", { name: /^Wyślij$/i }).click();
    await page.waitForFunction(
      () =>
        Array.isArray((window as any).__taskStreamEvents) &&
        (window as any).__taskStreamEvents.some(
          (event: { result?: string }) => event?.result === "SSE wynik odpowiedzi",
        ),
      undefined,
      { timeout: 10000 },
    );
  });
});
