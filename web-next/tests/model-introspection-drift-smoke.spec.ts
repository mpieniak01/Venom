import { expect, test } from "@playwright/test";

const MECHANISM_STORAGE_KEY = "venom.modelIntrospection.liveAnalysisEnabled";

function buildSnapshotResponse(modelName: string) {
  return {
    success: true,
    snapshot: {
      runtime: {
        provider: "multi_runtime",
        model: modelName,
        endpoint: "http://localhost:8014/v1",
        service_type: "local",
        mode: "LOCAL",
        label: `${modelName} · multi_runtime @ localhost:8014`,
        config_hash: "cfg-227",
        runtime_id: "multi_runtime@localhost:8014",
      },
      runtime_drift: {
        drift_detected: true,
        active_server: "multi_runtime",
        inferred_provider: "multi_runtime",
        model_name: modelName,
        endpoint: "http://localhost:8014/v1",
        issues: ["runtime_active_model differs from daemon_target_model"],
      },
      packages: {},
      available_packages: [],
      missing_packages: [],
      model_manager: {
        available: true,
        usage_metrics: null,
        error: null,
      },
      reuse: {
        brain: {
          path: "/brain",
          available: true,
          purpose: "reuse",
        },
        diagnostics: [],
      },
      summary: {
        active_model: modelName,
        provider: "multi_runtime",
        runtime_label: `${modelName} · multi_runtime @ localhost:8014`,
        introspection_ready: true,
      },
      graph: {
        nodes: [
          { id: "runtime", label: "runtime", kind: "runtime", status: "ok" },
          { id: "analysis", label: "analysis", kind: "analysis", status: "ok" },
        ],
        edges: [{ from: "runtime", to: "analysis", label: "edge:1" }],
        summary: {
          nodes: 2,
          edges: 1,
          available_packages: 0,
          missing_packages: 0,
          drift_issues: 1,
        },
      },
    },
  };
}

function buildDriftAnalysisSse(): string {
  const payload = {
    status: "skipped",
    skipped_reason: "model_drift_detected",
    analysis: {
      prompt: "Co to jest słońce?",
      response: "",
      chunk_count: 0,
      events: ["start", "done"],
      timeline: [
        { id: "snapshot_before", label: "Snapshot captured", status: "done", detail: "runtime ready", at_ms: 0 },
        { id: "request_ready", label: "Prompt prepared", status: "done", detail: "Co to jest słońce?", at_ms: 12 },
        { id: "analysis_skipped", label: "Analysis skipped", status: "skipped", detail: "Model drift detected", at_ms: 28 },
      ],
      elapsed_ms: 28,
      provider: "multi_runtime",
      model: "google/gemma-4-E2B-it",
      runtime_label: "google/gemma-4-E2B-it · multi_runtime @ localhost:8014",
      error: "MODEL_DRIFT_DETECTED",
      error_code: "MODEL_DRIFT_DETECTED",
    },
    snapshot_after: buildSnapshotResponse("google/gemma-4-E2B-it").snapshot,
  };

  return [
    `event: analysis_start\ndata: ${JSON.stringify(payload)}\n\n`,
    `event: analysis_done\ndata: ${JSON.stringify(payload)}\n\n`,
  ].join("");
}

test.describe("Model introspection drift smoke", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("venom-language", "pl");
      window.localStorage.setItem(MECHANISM_STORAGE_KEY, "true");
    });

    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url();
      if (url.includes("/api/v1/models/introspection/analyze/stream")) {
        await route.fulfill({
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
          body: buildDriftAnalysisSse(),
        });
        return;
      }
      if (url.includes("/api/v1/models/introspection")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(buildSnapshotResponse("google/gemma-4-E2B-it")),
        });
        return;
      }
      if (url.includes("/api/v1/tasks")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
        return;
      }
      if (url.includes("/api/v1/metrics/tokens")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ input_tokens: 0, output_tokens: 0, total_tokens: 0 }),
        });
        return;
      }
      if (url.includes("/api/v1/metrics")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({}),
        });
        return;
      }
      if (url.includes("/api/v1/models/usage")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ usage: {} }),
        });
        return;
      }
      if (url.includes("/api/v1/queue/status")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ pending: 0, completed: 0, failed: 0, total: 0 }),
        });
        return;
      }
      if (url.includes("/api/v1/system/services")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ services: [] }),
        });
        return;
      }
      if (url.includes("/api/v1/git/status")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ branch: "test", dirty: false, ahead: 0, behind: 0 }),
        });
        return;
      }
      if (url.includes("/api/v1/system/status")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ status: "ok" }),
        });
        return;
      }
      if (url.includes("/api/v1/system/llm-servers/active")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ status: "success", active_server: "multi_runtime", active_model: "google/gemma-4-E2B-it" }),
        });
        return;
      }
      if (url.includes("/api/v1/system/cost-mode")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ mode: "eco" }),
        });
        return;
      }
      if (url.includes("/api/v1/system/autonomy")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ level: "none", available: false }),
        });
        return;
      }
      if (url.includes("/api/v1/config/runtime")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({}),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });
  });

  test("manual runtime drift hard-fails analysis with dedicated code and runbook", async ({ page }) => {
    test.setTimeout(60_000);
    await page.goto("/inspector/model-introspection");
    await expect(page.getByRole("heading", { name: /Podgląd wnętrza modelu/i })).toBeVisible();
    await page.evaluate((storageKey) => {
      window.localStorage.setItem(storageKey, "true");
      window.dispatchEvent(new Event("venom:model-introspection-mechanism-change"));
    }, MECHANISM_STORAGE_KEY);
    const switches = page.getByRole("switch");
    const switchCount = await switches.count();
    for (let i = 0; i < switchCount; i += 1) {
      const sw = switches.nth(i);
      if (await sw.isVisible()) {
        const checked = await sw.getAttribute("aria-checked");
        if (checked !== "true") {
          await sw.click();
        }
      }
    }
    const runButton = page.getByRole("button", { name: /Uruchom analizę/i });
    await expect(runButton).toBeEnabled({ timeout: 15_000 });
    const analyzeRequest = page.waitForRequest((req) =>
      req.url().includes("/api/v1/models/introspection/analyze/stream"),
    );
    await runButton.click();
    await analyzeRequest;

    await expect(page.getByText(/drift present/i).first()).toBeVisible();
  });
});
