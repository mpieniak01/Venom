import { expect, test } from "@playwright/test";

const emptyJson = JSON.stringify([]);

test.describe("Cockpit streaming SSE", () => {
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
    const textarea = page.getByPlaceholder("Opisz zadanie dla Venoma...");
    await textarea.fill("Przetestuj strumień SSE");
    await page.getByRole("button", { name: /^Wyślij$/i }).click();
    await expect(page.getByText(/SSE wynik odpowiedzi/i).first()).toBeVisible();
  });
});
