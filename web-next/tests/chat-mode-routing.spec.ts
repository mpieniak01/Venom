import { expect, test, type Page } from "@playwright/test";

const emptyJson = JSON.stringify([]);

async function selectChatMode(page: Page, label: string) {
  const modeValueMap: Record<string, string> = {
    Direct: "direct",
    Normal: "normal",
    Complex: "complex",
  };
  const modeValue = modeValueMap[label] ?? label.toLowerCase();
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  const trigger = page.getByTestId("chat-mode-select");
  await trigger.waitFor({ state: "visible", timeout: 10000 });
  await trigger.click({ force: true });
  await page.getByTestId("chat-mode-menu").waitFor({ state: "visible", timeout: 10000 });
  const option = page.getByTestId(`chat-mode-option-${modeValue}`);
  await option.waitFor({ state: "visible", timeout: 10000 });
  await option.click({ force: true });
  await expect(trigger).toContainText(new RegExp(label.split(" ")[0], "i"));
}

async function waitForSessionReady(page: Page) {
  await page.waitForFunction(
    () => Boolean(window.localStorage.getItem("venom-session-id")),
    undefined,
    { timeout: 5000 },
  );
}

async function waitForCockpitReady(page: Page) {
  await page.getByTestId("cockpit-send-button").waitFor({ state: "visible", timeout: 10000 });
}

test.describe("Chat mode routing", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      const bootId = "boot-test";
      const sessionId = "session-test";
      window.localStorage.setItem("venom-session-id", sessionId);
      window.localStorage.setItem("venom-backend-boot-id", bootId);
      window.localStorage.setItem("venom-next-build-id", "test-build");
    });
    await page.route("**/api/v1/history/requests?limit=6", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
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

  test("Direct mode uses simple stream and skips tasks", async ({ page }) => {
    let simpleCalls = 0;
    let taskCalls = 0;
    let simpleBody: Record<string, unknown> | null = null;

    await page.route("**/api/v1/llm/simple/stream", async (route) => {
      simpleCalls += 1;
      simpleBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: "text/plain",
        body: "OK",
      });
    });

    await page.route("**/api/v1/tasks", async (route) => {
      if (route.request().method() === "POST") {
        taskCalls += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ task_id: "task-direct" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForSessionReady(page);
    await waitForCockpitReady(page);
    await selectChatMode(page, "Direct");
    await page.getByTestId("cockpit-prompt-input").fill("Test direct");
    const simpleRequest = page.waitForRequest(
      (req) =>
        req.url().includes("/api/v1/llm/simple/stream") && req.method() === "POST",
      { timeout: 10000 },
    );
    await page.getByTestId("cockpit-send-button").click();

    await simpleRequest;
    await expect.poll(() => simpleCalls, { timeout: 10000 }).toBeGreaterThan(0);
    expect(taskCalls).toBe(0);
    expect((simpleBody as any)?.session_id).toBeTruthy();
  });

  test("Normal mode routes through tasks without forced intent", async ({ page }) => {
    let taskBody: Record<string, unknown> | null = null;

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
            const payload = {
              event: "task_finished",
              data: JSON.stringify({ task_id: "task-normal", status: "COMPLETED", result: "OK" }),
            };
            const event = new MessageEvent(payload.event, { data: payload.data });
            (this.listeners[payload.event] || []).forEach((handler) => handler(event));
          }, 30);
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

    await page.route("**/api/v1/tasks", async (route) => {
      if (route.request().method() === "POST") {
        taskBody = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ task_id: "task-normal" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForSessionReady(page);
    await waitForCockpitReady(page);
    await selectChatMode(page, "Normal");
    await page.getByTestId("cockpit-prompt-input").fill("Test normal");
    const taskRequest = page.waitForRequest(
      (req) => req.url().includes("/api/v1/tasks") && req.method() === "POST",
      { timeout: 10000 },
    );
    await page.getByTestId("cockpit-send-button").click();

    await taskRequest;
    await expect.poll(() => taskBody, { timeout: 10000 }).not.toBeNull();
    expect((taskBody as any)?.forced_intent).toBeUndefined();
  });

  test("Complex mode forces COMPLEX_PLANNING intent and routes to Architect", async ({ page }) => {
    let taskBody: Record<string, unknown> | null = null;

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
                  task_id: "task-complex",
                  status: "PROCESSING",
                  logs: ["Zadanie sklasyfikowane jako COMPLEX_PLANNING - delegacja do Architekta"],
                }),
              },
              {
                event: "task_finished",
                data: JSON.stringify({
                  task_id: "task-complex",
                  status: "COMPLETED",
                  result: "OK",
                }),
              },
            ];
            payloads.forEach((payload, index) => {
              setTimeout(() => {
                const event = new MessageEvent(payload.event, { data: payload.data });
                (this.listeners[payload.event] || []).forEach((handler) => handler(event));
              }, 80 * (index + 1));
            });
          }, 30);
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

    await page.route("**/api/v1/tasks", async (route) => {
      if (route.request().method() === "POST") {
        taskBody = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ task_id: "task-complex" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForSessionReady(page);
    await waitForCockpitReady(page);
    await selectChatMode(page, "Complex");
    await page.getByTestId("cockpit-prompt-input").fill("Test complex");
    const taskRequest = page.waitForRequest(
      (req) => req.url().includes("/api/v1/tasks") && req.method() === "POST",
      { timeout: 10000 },
    );
    await page.getByTestId("cockpit-send-button").click();

    await taskRequest;
    await expect.poll(() => taskBody, { timeout: 10000 }).not.toBeNull();
    expect((taskBody as any)?.forced_intent).toBe("COMPLEX_PLANNING");
  });

  test("Streaming TTFT shows partial before final result", async ({ page }) => {
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
                  task_id: "task-ttft",
                  status: "PROCESSING",
                  result: "Pierwszy fragment",
                }),
              },
              {
                event: "task_finished",
                data: JSON.stringify({
                  task_id: "task-ttft",
                  status: "COMPLETED",
                  result: "Pierwszy fragment + reszta",
                }),
              },
            ];
            payloads.forEach((payload, index) => {
              setTimeout(() => {
                const event = new MessageEvent(payload.event, { data: payload.data });
                (this.listeners[payload.event] || []).forEach((handler) => handler(event));
              }, 120 * (index + 1));
            });
          }, 40);
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

    await page.route("**/api/v1/tasks", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ task_id: "task-ttft" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: emptyJson,
      });
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForSessionReady(page);
    await waitForCockpitReady(page);
    await selectChatMode(page, "Normal");
    const chatHistory = page.getByTestId("cockpit-chat-history");
    await chatHistory.scrollIntoViewIfNeeded();
    await page.getByTestId("cockpit-prompt-input").fill("Test streaming");
    await page.evaluate(() => {
      // @ts-expect-error - attach timing markers in test runtime
      window.__ttftStart = performance.now();
    });
    const taskRequest = page.waitForRequest(
      (req) => req.url().includes("/api/v1/tasks") && req.method() === "POST",
      { timeout: 10000 },
    );
    await page.getByTestId("cockpit-send-button").click();

    await taskRequest;
    await page.waitForFunction(
      () =>
        Array.isArray((window as any).__taskStreamEvents) &&
        (window as any).__taskStreamEvents.some(
          (event: { result?: string }) => event?.result === "Pierwszy fragment",
        ),
      undefined,
      { timeout: 10000 },
    );
    const ttftMs = await page.evaluate(() => {
      // @ts-expect-error - read timing markers in test runtime
      return performance.now() - (window.__ttftStart || 0);
    });
    expect(ttftMs).toBeLessThan(3000);
    await page.waitForFunction(
      () =>
        Array.isArray((window as any).__taskStreamEvents) &&
        (window as any).__taskStreamEvents.some(
          (event: { result?: string }) => event?.result === "Pierwszy fragment + reszta",
        ),
      undefined,
      { timeout: 10000 },
    );
  });
});
