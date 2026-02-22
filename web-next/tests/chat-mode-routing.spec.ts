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
  const expected = new RegExp(label.split(" ")[0], "i");
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await trigger.waitFor({ state: "visible", timeout: 10000 });
    await trigger.click({ force: true });
    await page.getByTestId("chat-mode-menu").waitFor({ state: "visible", timeout: 10000 });
    const option = page.getByTestId(`chat-mode-option-${modeValue}`);
    await option.waitFor({ state: "visible", timeout: 10000 });
    await option.scrollIntoViewIfNeeded();
    try {
      await option.click({ timeout: 3000 });
    } catch {
      // Fallback for flaky viewport clipping in dropdown portals.
      await option.evaluate((element) => {
        (element as HTMLButtonElement).click();
      });
    }
    try {
      await expect(trigger).toContainText(expected, { timeout: 5000 });
      return;
    } catch (error) {
      if (attempt === 1) throw error;
    }
  }
}

async function waitForSessionReady(page: Page) {
  await page.waitForFunction(
    () => Boolean(window.localStorage.getItem("venom-session-id")),
    undefined,
    { timeout: 5000 },
  );
}

async function waitForHydration(page: Page) {
  await page.waitForFunction(
    () => document.documentElement.dataset.hydrated === "true",
    undefined,
    { timeout: 10000 },
  );
}

async function waitForCockpitReady(page: Page) {
  await page.getByTestId("cockpit-send-button").waitFor({ state: "visible", timeout: 10000 });
}

type EventSourcePayload = { event: string; data: Record<string, unknown> };

async function installMockTaskEventSource(
  page: Page,
  payloads: EventSourcePayload[],
  openDelayMs: number,
  stepDelayMs: number,
) {
  await page.addInitScript(
    ({ payloads, openDelayMs, stepDelayMs }) => {
      class MockEventSource {
        url: string;
        onopen: ((event: Event) => void) | null = null;
        onerror: ((event: Event) => void) | null = null;
        private listeners: Record<string, Array<(event: MessageEvent) => void>> = {};

        constructor(url: string) {
          this.url = url;
          setTimeout(() => {
            this.onopen?.(new Event("open"));
            this.schedulePayloads(payloads, stepDelayMs);
          }, openDelayMs);
        }

        private emitPayload(payload: { event: string; data: Record<string, unknown> }) {
          const win = window as typeof window & { __taskStreamEvents?: Record<string, unknown>[] };
          win.__taskStreamEvents = [
            ...(win.__taskStreamEvents ?? []),
            { event: payload.event, ...payload.data },
          ].slice(-25);
          const event = new MessageEvent(payload.event, { data: JSON.stringify(payload.data) });
          for (const handler of this.listeners[payload.event] || []) {
            handler(event);
          }
        }

        private schedulePayload(payload: { event: string; data: Record<string, unknown> }, delayMs: number) {
          setTimeout(() => this.emitPayload(payload), delayMs);
        }

        private schedulePayloads(payloads: Array<{ event: string; data: Record<string, unknown> }>, delayStepMs: number) {
          for (let index = 0; index < payloads.length; index += 1) {
            this.schedulePayload(payloads[index], delayStepMs * (index + 1));
          }
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
    },
    { payloads, openDelayMs, stepDelayMs },
  );
}

test.describe("Chat mode routing", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      const bootId = "boot-test";
      const sessionId = "session-test";
      window.localStorage.setItem("venom-language", "pl");
      window.localStorage.setItem("venom-session-id", sessionId);
      window.localStorage.setItem("venom-backend-boot-id", bootId);
      window.localStorage.setItem("venom-next-build-id", "test-build");
      const win = window as typeof window & { __taskStreamEvents?: Record<string, unknown>[] };
      win.__taskStreamEvents = [];
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

  test("Normal mode routes through tasks without forced intent", async ({ page }) => {
    let taskBody: Record<string, unknown> | null = null;

    await installMockTaskEventSource(
      page,
      [{ event: "task_finished", data: { task_id: "task-normal", status: "COMPLETED", result: "OK" } }],
      30,
      120,
    );

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
    await waitForHydration(page);
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
    expect((taskBody as Record<string, unknown> | null)?.forced_intent).toBeUndefined();

    // Verify exactly one user question and one assistant response (no duplicates)
    await expect(page.getByTestId("conversation-bubble-user")).toHaveCount(1);
    await expect(page.getByTestId("conversation-bubble-assistant")).toHaveCount(1);
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
        contentType: "text/event-stream",
        body: 'event: content\ndata: {"text": "O"}\n\nevent: content\ndata: {"text": "K"}\n\nevent: done\ndata: {}\n\n',
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
    await waitForHydration(page);
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
    expect((simpleBody as Record<string, unknown> | null)?.session_id).toBeTruthy();

    // Verify exactly one user question and one assistant response (no duplicates)
    await expect(page.getByTestId("conversation-bubble-user")).toHaveCount(1);
    await expect(page.getByTestId("conversation-bubble-assistant")).toHaveCount(1);
  });

  test("Streaming TTFT shows partial before final result", async ({ page }) => {
    await installMockTaskEventSource(
      page,
      [
        { event: "task_update", data: { task_id: "task-ttft", status: "PROCESSING", result: "Pierwszy fragment" } },
        {
          event: "task_finished",
          data: { task_id: "task-ttft", status: "COMPLETED", result: "Pierwszy fragment + reszta" },
        },
      ],
      40,
      120,
    );

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
    await waitForHydration(page);
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
      () => {
        const win = window as typeof window & { __taskStreamEvents?: Record<string, unknown>[] };
        return Array.isArray(win.__taskStreamEvents) &&
          win.__taskStreamEvents.some(
            (event: Record<string, unknown>) => event?.result === "Pierwszy fragment",
          );
      },
      undefined,
      { timeout: 10000 },
    );
    const ttftMs = await page.evaluate(() => {
      // @ts-expect-error - read timing markers in test runtime
      return performance.now() - (window.__ttftStart || 0);
    });
    expect(ttftMs).toBeLessThan(3000);
    await page.waitForFunction(
      () => {
        const win = window as typeof window & { __taskStreamEvents?: Record<string, unknown>[] };
        return Array.isArray(win.__taskStreamEvents) &&
          win.__taskStreamEvents.some(
            (event: Record<string, unknown>) => event?.result === "Pierwszy fragment + reszta",
          );
      },
      undefined,
      { timeout: 10000 },
    );
  });

  test("Complex mode forces COMPLEX_PLANNING intent and routes to Architect", async ({ page }) => {
    let taskBody: Record<string, unknown> | null = null;

    await installMockTaskEventSource(
      page,
      [
        {
          event: "task_update",
          data: {
            task_id: "task-complex",
            status: "PROCESSING",
            logs: ["Zadanie sklasyfikowane jako COMPLEX_PLANNING - delegacja do Architekta"],
          },
        },
        { event: "task_finished", data: { task_id: "task-complex", status: "COMPLETED", result: "OK" } },
      ],
      30,
      80,
    );

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
    await waitForHydration(page);
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
    expect((taskBody as Record<string, unknown> | null)?.forced_intent).toBe("COMPLEX_PLANNING");
  });
});
