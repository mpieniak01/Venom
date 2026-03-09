import { test } from "@playwright/test";
import { ensureChatRuntimeReadyOrSkip } from "./utils/chat-runtime-readiness";

const emptyJson = JSON.stringify([]);

type StreamPayload = { event: string; data: Record<string, unknown> };

const streamPayloads: StreamPayload[] = [
  {
    event: "task_update",
    data: {
      task_id: "sse-test-123",
      status: "PROCESSING",
      logs: ["Rozpoczynam streaming odpowiedzi"],
    },
  },
  {
    event: "task_finished",
    data: {
      task_id: "sse-test-123",
      status: "COMPLETED",
      result: "SSE wynik odpowiedzi",
    },
  },
];

async function registerRuntimeContractRoutes(
  page: import("@playwright/test").Page,
  {
    runtimeId = "ollama",
    modelName = "gemma2:2b",
  }: { runtimeId?: string; modelName?: string } = {},
) {
  await page.route("**/api/v1/system/llm-runtime/options**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "success",
        active: {
          runtime_id: runtimeId,
          active_server: runtimeId,
          active_model: modelName,
          active_endpoint: "http://127.0.0.1:11434/v1",
          config_hash: "test-hash",
          source_type: "local-runtime",
        },
        runtimes: [
          {
            runtime_id: runtimeId,
            source_type: "local-runtime",
            configured: true,
            available: true,
            status: "online",
            reason: null,
            active: true,
            adapter_deploy_supported: true,
            adapter_deploy_mode: "ollama_modelfile",
            supports_native_training: false,
            supports_adapter_import_safetensors: true,
            supports_adapter_import_gguf: true,
            supports_adapter_runtime_apply: true,
            models: [
              {
                id: modelName,
                name: modelName,
                provider: runtimeId.toLowerCase(),
                runtime_id: runtimeId,
                source_type: "local-runtime",
                active: true,
                chat_compatible: true,
                canonical_model_id: "gemma-2-2b-it",
              },
            ],
          },
        ],
        model_catalog: {
          all_models: [{
            id: modelName,
            name: modelName,
            provider: runtimeId.toLowerCase(),
            runtime_id: runtimeId,
            source_type: "local-runtime",
            active: true,
            chat_compatible: true,
            canonical_model_id: "gemma-2-2b-it",
          }],
          chat_models: [{
            id: modelName,
            name: modelName,
            provider: runtimeId.toLowerCase(),
            runtime_id: runtimeId,
            source_type: "local-runtime",
            active: true,
            chat_compatible: true,
            canonical_model_id: "gemma-2-2b-it",
          }],
          runtime_servable_models: [{
            id: modelName,
            name: modelName,
            provider: runtimeId.toLowerCase(),
            runtime_id: runtimeId,
            source_type: "local-runtime",
            active: true,
            chat_compatible: true,
            canonical_model_id: "gemma-2-2b-it",
          }],
        },
      }),
    });
  });
  await page.route("**/api/v1/system/llm-servers/active**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "success",
        active_server: runtimeId,
        active_model: modelName,
        active_endpoint: "http://127.0.0.1:11434/v1",
        config_hash: "test-hash",
        runtime_id: runtimeId,
        source_type: "local-runtime",
      }),
    });
  });
}

async function installStreamingMockEventSource(page: import("@playwright/test").Page) {
  await page.addInitScript(({ payloads }) => {
    class MockEventSource {
      url: string;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      private listeners: Record<string, Array<(event: MessageEvent) => void>> = {};

      constructor(url: string) {
        this.url = url;
        setTimeout(() => {
          this.onopen?.(new Event("open"));
          this.schedulePayloads(payloads);
        }, 50);
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

      private schedulePayloads(payloads: Array<{ event: string; data: Record<string, unknown> }>) {
        for (let index = 0; index < payloads.length; index += 1) {
          this.schedulePayload(payloads[index], 150 * (index + 1));
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
  }, { payloads: streamPayloads });
}

test.describe("Cockpit streaming SSE", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("venom-session-id", "session-test");
      window.localStorage.setItem("venom-backend-boot-id", "boot-test");
      window.localStorage.setItem("venom-next-build-id", "test-build");
      window.localStorage.setItem("venom-language", "pl");
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
    await registerRuntimeContractRoutes(page);
  });

  test("aktualizuje bąbel rozmowy po zdarzeniach SSE", async ({ page }) => {
    await installStreamingMockEventSource(page);

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
    await page.waitForFunction(
      () => document.documentElement.dataset.hydrated === "true",
      undefined,
      { timeout: 10000 },
    );
    if (!(await ensureChatRuntimeReadyOrSkip(page))) return;
    const chatHistory = page.getByTestId("cockpit-chat-history");
    await chatHistory.scrollIntoViewIfNeeded();
    const textarea = page.getByTestId("cockpit-prompt-input");
    await textarea.fill("Przetestuj strumień SSE");
    await page.getByTestId("cockpit-send-button").click();
    await page.waitForFunction(
      () => {
        const win = window as typeof window & { __taskStreamEvents?: Record<string, unknown>[] };
        return Array.isArray(win.__taskStreamEvents) &&
          win.__taskStreamEvents.some(
            (event: Record<string, unknown>) => event?.result === "SSE wynik odpowiedzi",
          );
      },
      undefined,
      { timeout: 10000 },
    );
  });
});
