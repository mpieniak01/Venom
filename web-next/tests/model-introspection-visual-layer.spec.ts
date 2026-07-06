import { expect, test } from "@playwright/test";

const MECHANISM_STORAGE_KEY = "venom.modelIntrospection.liveAnalysisEnabled";

function makeArchitectureGraphFixture() {
  return {
    nodes: [
      {
        id: "input",
        label: "input embeddings",
        kind: "input",
        status: "ready",
        role: "input",
        layer_index: 0,
        group: "entry",
      },
      {
        id: "embedding",
        label: "token embedding",
        kind: "embedding",
        status: "ready",
        role: "embedding",
        layer_index: 0,
        group: "embedding",
      },
      {
        id: "layer_1",
        label: "transformer block 1",
        kind: "layer",
        status: "ready",
        role: "layer",
        layer_index: 1,
        group: "sliding_attention",
      },
      {
        id: "layer_2",
        label: "transformer block 2",
        kind: "layer",
        status: "ready",
        role: "layer",
        layer_index: 2,
        group: "full_attention",
      },
      {
        id: "layer_3",
        label: "transformer block 3",
        kind: "layer",
        status: "ready",
        role: "layer",
        layer_index: 3,
        group: "sliding_attention",
      },
      {
        id: "output",
        label: "logits",
        kind: "output",
        status: "ready",
        role: "output",
        layer_index: 4,
        group: "exit",
      },
      {
        id: "probe",
        label: "probe surface",
        kind: "attention",
        status: "ready",
        role: "attention",
        layer_index: 3,
        group: "probe",
      },
      {
        id: "residual",
        label: "residual merge",
        kind: "residual",
        status: "ready",
        role: "residual",
        layer_index: 3,
        group: "residual",
      },
    ],
    edges: [
      { from: "input", to: "embedding", label: "tokenize", direction: "forward" },
      { from: "embedding", to: "layer_1", label: "enter stack", direction: "forward" },
      { from: "layer_1", to: "layer_2", label: "full_attention", direction: "forward" },
      { from: "layer_2", to: "layer_3", label: "sliding_attention", direction: "forward" },
      { from: "layer_3", to: "probe", label: "probe path", direction: "forward" },
      { from: "layer_3", to: "residual", label: "residual path", direction: "forward" },
      { from: "probe", to: "residual", label: "merge", direction: "forward" },
      { from: "residual", to: "output", label: "decode", direction: "forward" },
    ],
    summary: {
      nodes: 8,
      edges: 8,
      layer_count: 3,
      block_count: 3,
    },
    meta: {
      runtime: "gemma-4-E2B-it · multi_runtime @ localhost:8014",
      model: "google/gemma-4-E2B-it",
      provider: "multi_runtime",
      generated_at: "2026-05-27T10:00:00Z",
      fidelity: "native",
      source: "native runtime config",
      source_path: "/home/ubuntu/venom/data/models/self_learning_test/runtime_vllm/config.json",
      base_model: "google/gemma-3-4b-it",
    },
  };
}

function makeGraphFixture() {
  return {
    nodes: [
      {
        id: "runtime",
        label: "gemma-4-E2B-it · multi_runtime @ localhost:8014",
        kind: "runtime",
        status: "multi_runtime",
      },
      {
        id: "model",
        label: "google/gemma-4-E2B-it",
        kind: "model",
        status: "active",
      },
      {
        id: "analysis",
        label: "live analysis",
        kind: "analysis",
        status: "ready",
      },
      {
        id: "manager",
        label: "ModelManager",
        kind: "manager",
        status: "connected",
      },
      { id: "brain", label: "/brain", kind: "reuse", status: "available" },
      {
        id: "diagnostics",
        label: "runtime diagnostics",
        kind: "reuse",
        status: "available",
      },
      {
        id: "package:captum",
        label: "captum",
        kind: "package",
        status: "available",
      },
      {
        id: "package:transformer-lens",
        label: "transformer-lens",
        kind: "package",
        status: "available",
      },
    ],
    edges: [
      { from: "runtime", to: "model", label: "active model" },
      { from: "runtime", to: "analysis", label: "prompt execution" },
      { from: "runtime", to: "manager", label: "usage metrics" },
      { from: "runtime", to: "brain", label: "reuse" },
      { from: "runtime", to: "diagnostics", label: "reuse" },
      { from: "model", to: "package:captum", label: "optional" },
      { from: "model", to: "package:transformer-lens", label: "optional" },
    ],
    summary: {
      nodes: 8,
      edges: 7,
      available_packages: 2,
      missing_packages: 0,
      drift_issues: 0,
    },
  };
}

function makeSnapshot() {
  return {
    runtime: {
      provider: "multi_runtime",
      model: "google/gemma-4-E2B-it",
      endpoint: "http://localhost:8014/v1",
      service_type: "local",
      mode: "LOCAL",
      label: "google/gemma-4-E2B-it · multi_runtime @ localhost:8014",
      config_hash: "cfg-249h",
      runtime_id: "multi_runtime@localhost:8014",
    },
    runtime_drift: {
      drift_detected: false,
      active_server: "multi_runtime",
      inferred_provider: "multi_runtime",
      model_name: "google/gemma-4-E2B-it",
      endpoint: "http://localhost:8014/v1",
      issues: [],
    },
    packages: {
      captum: {
        module: "captum",
        package: "captum",
        available: true,
        version: "0.9.0",
      },
      "transformer-lens": {
        module: "transformer_lens",
        package: "transformer-lens",
        available: true,
        version: "3.2.1",
      },
    },
    available_packages: ["captum", "transformer-lens"],
    missing_packages: [],
    model_manager: {
      available: true,
      usage_metrics: {
        models_count: 2,
        memory_usage_mb: 512,
        vram_usage_mb: 2048,
      },
      error: null,
    },
    reuse: {
      brain: {
        path: "/brain",
        available: true,
        purpose: "existing rag and graph surface",
      },
      diagnostics: [],
    },
    summary: {
      active_model: "google/gemma-4-E2B-it",
      provider: "multi_runtime",
      runtime_label: "google/gemma-4-E2B-it · multi_runtime @ localhost:8014",
      introspection_ready: true,
    },
    graph: makeGraphFixture(),
    architecture_graph: makeArchitectureGraphFixture(),
  };
}

test.describe("Model introspection visual information layer", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("venom-language", "en");
      window.localStorage.setItem(MECHANISM_STORAGE_KEY, "true");
    });

    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url();
      if (url.includes("/api/v1/models/introspection/analyze/stream")) {
        await route.fulfill({
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
          body: "event: done\ndata: {}\n\n",
        });
        return;
      }
      if (url.includes("/api/v1/models/introspection/analyze")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ success: true, snapshot: makeSnapshot() }),
        });
        return;
      }
      if (url.includes("/api/v1/models/introspection")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ success: true, snapshot: makeSnapshot() }),
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
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });
  });

  test("desktop: exposes visual mode controls and toggles overview/detail", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.goto("/inspector/model-introspection");
    await expect(
      page.getByRole("heading", { name: /Model interior view|Podgląd wnętrza modelu/i }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: /Refresh snapshot|Odśwież snapshot|Odśwież migawkę/i })
      .click();

    await expect(page.getByRole("heading", { name: /Architecture graph|Graf architektury/i })).toBeVisible();
    const overviewButton = page.getByTestId("architecture-mode-overview");
    const detailButton = page.getByTestId("architecture-mode-detail");
    await expect(overviewButton).toBeVisible();
    await expect(detailButton).toBeVisible();
    await expect(page.getByText(/replaces text|zastępuje tekst/i)).toBeVisible();
    await expect(page.getByText(/supports text|wspiera tekst/i)).toBeVisible();
    await expect(page.getByText(/evidence only|tylko dowody/i)).toBeVisible();
    await expect(page.getByText(/Local relation map|Lokalna mapa relacji/i)).toBeVisible();
    await expect(page.locator('[data-testid^="architecture-relation-"][aria-pressed="true"]')).toBeVisible();

    const initialSnapshot = await page.evaluate(() => ({
      overviewPressed:
        document.querySelector('[data-testid="architecture-mode-overview"]')?.getAttribute("aria-pressed"),
      detailPressed:
        document.querySelector('[data-testid="architecture-mode-detail"]')?.getAttribute("aria-pressed"),
    }));
    expect(initialSnapshot).toEqual({ overviewPressed: "false", detailPressed: "true" });

    await overviewButton.click();
    await expect(page.getByText(/Architecture overview|Przegląd architektury/i)).toBeVisible();
    await expect(page.getByText(/Local relation map|Lokalna mapa relacji/i)).toBeVisible();
    await page.locator('[data-testid^="architecture-relation-"]').nth(1).click();
    await expect(page.locator('[data-testid^="architecture-relation-"][aria-pressed="true"]')).toBeVisible();
    await detailButton.click();
    await expect(page.getByText(/Layer internals|Wnętrze warstwy/i)).toBeVisible();
  });

  test("mobile: keeps overview/detail controls visible after snapshot load", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/inspector/model-introspection");
    await page
      .getByRole("button", { name: /Refresh snapshot|Odśwież snapshot|Odśwież migawkę/i })
      .click();

    await expect(page.getByRole("heading", { name: /Architecture graph|Graf architektury/i })).toBeVisible();
    await expect(page.getByTestId("architecture-mode-overview")).toBeVisible();
    await expect(page.getByTestId("architecture-mode-detail")).toBeVisible();
    await expect(page.getByText(/Local relation map|Lokalna mapa relacji/i)).toBeVisible();
  });
});
