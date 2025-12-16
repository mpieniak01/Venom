import { expect, test } from "@playwright/test";

const emptyJson = JSON.stringify([]);

test.describe("Cockpit streaming SSE", () => {
  test("aktualizuje bąbel rozmowy po zdarzeniach SSE", async ({ page }) => {
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

    await page.route("**/api/v1/tasks/*/stream", async (route) => {
      const url = new URL(route.request().url());
      const match = url.pathname.match(/tasks\/([^/]+)\/stream/);
      const taskId = match ? match[1] : "sse-test-123";
      const streamBody = [
        "event:task_update",
        `data:${JSON.stringify({
          task_id: taskId,
          status: "PROCESSING",
          logs: ["Rozpoczynam streaming odpowiedzi"],
        })}`,
        "",
        "event:task_finished",
        `data:${JSON.stringify({
          task_id: taskId,
          status: "COMPLETED",
          result: "SSE wynik odpowiedzi",
        })}`,
        "",
      ].join("\n");

      await route.fulfill({
        status: 200,
        headers: {
          "Cache-Control": "no-cache",
        },
        contentType: "text/event-stream",
        body: streamBody,
      });
    });

    await page.goto("/");
    const textarea = page.getByPlaceholder("Opisz zadanie dla Venoma...");
    await textarea.fill("Przetestuj strumień SSE");
    await page.getByRole("button", { name: /^Wyślij$/i }).click();
    await expect(page.getByText(/SSE wynik odpowiedzi/i).first()).toBeVisible();
  });
});
