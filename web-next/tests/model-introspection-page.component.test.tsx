import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LanguageProvider } from "../lib/i18n";
import { ModelIntrospectionDashboard } from "../components/inspector/model-introspection-dashboard";
import { ModelIntrospectionMechanismProvider } from "../components/inspector/model-introspection-mechanism";

afterEach(() => cleanup());

const originalFetch = globalThis.fetch;
const mechanismStorageKey = "venom.modelIntrospection.liveAnalysisEnabled";

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

function makeRuntimeFixture() {
  return {
    provider: "multi_runtime",
    model: "google/gemma-4-E2B-it",
    endpoint: "http://localhost:8014/v1",
    service_type: "local",
    mode: "LOCAL",
    label: "gemma-4-E2B-it · multi_runtime @ localhost:8014",
    config_hash: "abc123",
    runtime_id: "multi_runtime@http://localhost:8014/v1",
  };
}

function makeSnapshotBeforeFixture() {
  return {
    runtime: makeRuntimeFixture(),
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
      diagnostics: [{ id: "217da", purpose: "runtime lifecycle diagnostics" }],
    },
    summary: {
      active_model: "google/gemma-4-E2B-it",
      provider: "multi_runtime",
      runtime_label: "gemma-4-E2B-it · multi_runtime @ localhost:8014",
      introspection_ready: true,
    },
    graph: makeGraphFixture(),
  };
}

function makeSnapshotAfterFixture() {
  return {
    runtime: makeRuntimeFixture(),
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
    },
    available_packages: ["captum"],
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
        purpose: "existing rag and graph surface",
      },
      diagnostics: [{ id: "217da", purpose: "runtime lifecycle diagnostics" }],
    },
    summary: {
      active_model: "google/gemma-4-E2B-it",
      provider: "multi_runtime",
      runtime_label: "gemma-4-E2B-it · multi_runtime @ localhost:8014",
      introspection_ready: true,
    },
    graph: makeGraphFixture(),
  };
}

function makeAnalysisRunningPayload() {
  const snapshot = makeSnapshotBeforeFixture();
  return {
    analysis_enabled: true,
    status: "running",
    snapshot,
    snapshot_after: null,
    analysis: {
      prompt: "Co to jest slonce?",
      response: "",
      chunk_count: 0,
      events: [],
      timeline: [
        {
          id: "snapshot_before",
          label: "Snapshot captured",
          status: "done",
          detail: snapshot.runtime.label,
          at_ms: 0,
        },
        {
          id: "request_ready",
          label: "Prompt prepared",
          status: "done",
          detail: "Co to jest slonce?",
          at_ms: 0,
        },
        {
          id: "stream_opened",
          label: "Stream opened",
          status: "running",
          detail: "Awaiting streamed content",
          at_ms: 0,
        },
      ],
      elapsed_ms: 0,
      provider: snapshot.runtime.provider,
      model: snapshot.runtime.model,
      runtime_label: snapshot.runtime.label,
      request_ready_ms: 0,
      response_received_ms: null,
      snapshot_after_ms: null,
      process: null,
    },
  };
}

function makeAnalysisCompletedPayload() {
  const snapshot = makeSnapshotBeforeFixture();
  const snapshotAfter = makeSnapshotAfterFixture();
  return {
    analysis_enabled: true,
    status: "completed",
    snapshot,
    snapshot_after: snapshotAfter,
    analysis: {
      prompt: "Co to jest slonce?",
      response: "Slonce to gwiazda.",
      chunk_count: 2,
      events: ["start", "content", "content", "done"],
      timeline: [
        {
          id: "snapshot_before",
          label: "Snapshot captured",
          status: "done",
          detail: snapshot.runtime.label,
          at_ms: 0,
        },
        {
          id: "request_ready",
          label: "Prompt prepared",
          status: "done",
          detail: "Co to jest slonce?",
          at_ms: 0,
        },
        {
          id: "stream_opened",
          label: "Stream opened",
          status: "done",
          detail: "4 event(s) observed",
          at_ms: 10.2,
        },
        {
          id: "first_chunk",
          label: "First content chunk",
          status: "done",
          detail: "1 chunk(s) total",
          at_ms: 18.4,
        },
        {
          id: "response_finalized",
          label: "Response assembled",
          status: "done",
          detail: "18 chars",
          at_ms: 61.7,
        },
        {
          id: "attention_probe",
          label: "Attention probe",
          status: "failed",
          detail: "probe_transport_error",
          reason_code: "probe_transport_error",
          path: "internals_path",
          at_ms: 61.7,
          progress: 93,
        },
        {
          id: "snapshot_after",
          label: "Snapshot refreshed",
          status: "done",
          detail: "1 packages available",
          at_ms: 61.7,
        },
      ],
      timeline_step_count: 7,
      elapsed_ms: 61.7,
      provider: snapshot.runtime.provider,
      model: snapshot.runtime.model,
      runtime_label: snapshot.runtime.label,
      request_ready_ms: 0,
      response_received_ms: 10.2,
      snapshot_after_ms: 61.7,
      process: {
        request_id: "8fd5af48-7d34-4f69-90e2-3e6b2c2a1c11",
        status: "COMPLETED",
        step_count: 4,
        steps: [
          {
            component: "SimpleMode",
            action: "request",
            status: "ok",
            details: "session_id=- prompt=Co to jest slonce?",
          },
          {
            component: "SimpleMode",
            action: "context_preview",
            status: "ok",
            details: JSON.stringify({
              mode: "direct",
              prompt_context_truncated: false,
              hidden_prompts_count: 0,
            }),
            prompt_context_truncated: false,
            hidden_prompts_count: 0,
          },
          {
            component: "SimpleMode",
            action: "first_chunk",
            status: "ok",
            details: "elapsed_ms=18 preview=Slonce to gwiazda.",
            elapsed_ms: 18,
          },
          {
            component: "SimpleMode",
            action: "response",
            status: "ok",
            details: JSON.stringify({
              chunks: 2,
              total_ms: 61.7,
              chars: 18,
              response: "Slonce to gwiazda.",
              truncated: false,
            }),
            chunks: 2,
            total_ms: 61.7,
            chars: 18,
            truncated: false,
          },
        ],
        first_chunk_ms: 18,
        response_chunks: 2,
        response_chars: 18,
        total_ms: 61.7,
        chars_per_second: 291.46,
        response_truncated: false,
        prompt_trimmed: false,
        context_preview_truncated: false,
        adapter_applied: false,
        adapter_id: null,
      },
      logit_lens: {
        source: "probe_runtime",
        status: "ok",
        code: null,
        message: null,
        runtime_label: snapshot.runtime.label,
        input_tokens: ["▁Co", "▁to", "▁jest"],
        output_tokens: ["▁Słońce", "▁to", "▁gwiazda"],
        checkpoints: [
          {
            id: "cp_25",
            percent: 25,
            layer: 4,
            top_k: [
              { token: "▁Słońce", token_index: 0, score: 8.125 },
              { token: "▁gwiazda", token_index: 1, score: 7.75 },
            ],
            top_token: "▁Słońce",
            confidence: 0.42,
            changed: false,
          },
        ],
        signals: {
          early_unstable: false,
          late_stabilized: true,
          low_confidence_path: false,
        },
        interpretability: {
          interpretable: true,
          confidence_band: "high",
          token_noise_ratio: 0.18,
          readable_top_tokens: 2,
          total_top_tokens: 2,
        },
        diagnostics: { elapsed_ms: 12.4 },
      },
      analysis_capabilities: {
        attention: {
          available: true,
          source: "probe_runtime",
          status: "ok",
          reason: "attention_proxy_logits",
        },
        saliency: {
          available: true,
          source: "probe_runtime",
          status: "ok",
          reason: "saliency_proxy_attention",
        },
        logit_lens: {
          available: true,
          source: "probe_runtime",
          status: "ok",
          reason: "ok",
        },
        available_count: 3,
        total_count: 3,
        probe_profile: "dev",
        probe_enabled: true,
        probe_healthy: true,
        runtime_supported: true,
        endpoint_configured: true,
        model_whitelisted: true,
        limits: {
          timeout_seconds: 25,
          max_attempts: 2,
          max_top_k: 32,
          max_layer_count: 8,
          max_head_count: 32,
          max_prompt_tokens: 1024,
        },
        internals_verdict: "full",
      },
    },
  };
}

function createStreamingAnalysisResponse() {
  const encoder = new TextEncoder();
  const events = [
    { delayMs: 0, payload: `event: analysis_start\ndata: ${JSON.stringify(makeAnalysisRunningPayload())}\n\n` },
    { delayMs: 0, payload: "event: start\ndata: {}\n\n" },
    { delayMs: 0, payload: 'event: content\ndata: {"text":"Slonce to "}\n\n' },
    { delayMs: 120, payload: 'event: content\ndata: {"text":"gwiazda."}\n\n' },
    { delayMs: 120, payload: "event: done\ndata: {}\n\n" },
    { delayMs: 0, payload: `event: analysis_done\ndata: ${JSON.stringify(makeAnalysisCompletedPayload())}\n\n` },
  ];
  return new Response(
    new ReadableStream({
      start(controller) {
        let index = 0;
        const push = () => {
          if (index >= events.length) {
            controller.close();
            return;
          }
          const next = events[index++];
          controller.enqueue(encoder.encode(next.payload));
          setTimeout(push, next.delayMs);
        };
        push();
      },
    }),
    {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
      },
    },
  );
}

beforeEach(() => {
  globalThis.window.localStorage.setItem(mechanismStorageKey, "true");
  globalThis.fetch = async (input: RequestInfo | URL) => {
    const url = String(input);
    if (!url.includes("/api/v1/models/introspection")) {
      throw new Error(`Unexpected fetch URL: ${url}`);
    }
    if (url.includes("/api/v1/models/introspection/analyze/stream")) {
      return createStreamingAnalysisResponse();
    }
    if (url.includes("/api/v1/models/introspection/analyze")) {
      return new Response(
        JSON.stringify({
          success: true,
          snapshot: {
            status: "completed",
            analysis: {
              prompt: "Co to jest slonce?",
              response: "Slonce to gwiazda.",
              chunk_count: 1,
              events: ["start", "content", "done"],
              timeline: [
                {
                  id: "snapshot_before",
                  label: "Snapshot captured",
                  status: "done",
                  detail: "gemma-4-E2B-it · multi_runtime @ localhost:8014",
                  at_ms: 0,
                },
                {
                  id: "request_ready",
                  label: "Prompt prepared",
                  status: "done",
                  detail: "Co to jest slonce?",
                  at_ms: 0,
                },
                {
                  id: "stream_opened",
                  label: "Stream opened",
                  status: "done",
                  detail: "3 event(s) observed",
                  at_ms: 12.4,
                },
                {
                  id: "response_finalized",
                  label: "Response assembled",
                  status: "done",
                  detail: "18 chars",
                  at_ms: 321.4,
                },
              ],
              elapsed_ms: 321.4,
              provider: "multi_runtime",
              model: "google/gemma-4-E2B-it",
              runtime_label: "gemma-4-E2B-it · multi_runtime @ localhost:8014",
            },
            snapshot_after: {
              runtime: {
                provider: "multi_runtime",
                model: "google/gemma-4-E2B-it",
                endpoint: "http://localhost:8014/v1",
                service_type: "local",
                mode: "LOCAL",
                label: "gemma-4-E2B-it · multi_runtime @ localhost:8014",
                config_hash: "abc123",
                runtime_id: "multi_runtime@http://localhost:8014/v1",
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
              },
              available_packages: ["captum"],
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
                  purpose: "existing rag and graph surface",
                },
                diagnostics: [
                  { id: "217da", purpose: "runtime lifecycle diagnostics" },
                ],
              },
              summary: {
                active_model: "google/gemma-4-E2B-it",
                provider: "multi_runtime",
                runtime_label: "gemma-4-E2B-it · multi_runtime @ localhost:8014",
                introspection_ready: true,
              },
              graph: makeGraphFixture(),
            },
          },
        }),
        { status: 200 },
      );
    }
    return new Response(
      JSON.stringify({
        success: true,
        snapshot: {
          runtime: {
            provider: "multi_runtime",
            model: "google/gemma-4-E2B-it",
            endpoint: "http://localhost:8014/v1",
            service_type: "local",
            mode: "LOCAL",
            label: "gemma-4-E2B-it · multi_runtime @ localhost:8014",
            config_hash: "abc123",
            runtime_id: "multi_runtime@http://localhost:8014/v1",
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
            diagnostics: [
              { id: "217da", purpose: "runtime lifecycle diagnostics" },
            ],
          },
          summary: {
            active_model: "google/gemma-4-E2B-it",
            provider: "multi_runtime",
            runtime_label: "gemma-4-E2B-it · multi_runtime @ localhost:8014",
            introspection_ready: true,
          },
          graph: makeGraphFixture(),
        },
      }),
      { status: 200 },
    );
  };
});

afterEach(() => {
  globalThis.window.localStorage.removeItem(mechanismStorageKey);
  globalThis.fetch = originalFetch;
});

describe("ModelIntrospectionDashboard", () => {
  it("renders snapshot data and navigation links", async () => {
    render(
      <LanguageProvider>
        <ModelIntrospectionMechanismProvider>
          <ModelIntrospectionDashboard />
        </ModelIntrospectionMechanismProvider>
      </LanguageProvider>,
    );

    await waitFor(() => {
      assert.ok(
        screen.getByText(
          /Podgląd wnętrza modelu|Model interior view|Blick ins Modellinnere/i,
        ),
      );
    });
    assert.ok(
      screen.getAllByText("gemma-4-E2B-it · multi_runtime @ localhost:8014").length >= 1,
    );
    assert.ok(screen.getByRole("link", { name: "Open Knowledge Graph" }));
    assert.ok(screen.getByLabelText("Prompt"));
    const technicalLayerToggle = screen.getByRole("button", {
      name: /Show technical layer|Hide technical layer/i,
    });
    assert.ok(technicalLayerToggle);
    fireEvent.click(technicalLayerToggle);
    assert.ok(screen.getByText("Graph view"));
    assert.ok(screen.getAllByText("Graph drilldown").length >= 1);
    assert.ok(screen.getByRole("button", { name: "Select graph node gemma-4-E2B-it · multi_runtime @ localhost:8014" }));

    assert.ok(screen.getByText("Runtime details"));
    assert.ok(screen.getByText("Provider: multi_runtime"));

    fireEvent.click(screen.getByRole("button", { name: "Select graph node captum" }));
    assert.ok(screen.getByText("Package details"));
    assert.ok(screen.getByText("Package: captum"));

    fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));

    await waitFor(() => {
      assert.ok(screen.getByText("Snapshot captured"));
      assert.ok(screen.getByText("Prompt prepared"));
      assert.ok(screen.getByText("First content chunk"));
      assert.ok(screen.getByText("typing..."));
      assert.ok(screen.getAllByText(/Slonce to/i).length >= 1);
    });

    assert.equal(screen.queryByText("Response assembled"), null);

    await waitFor(() => {
      assert.ok(screen.getByText("Response assembled"));
      assert.ok(screen.getByText("2 chunk(s) · 7 step(s) · completed"));
      assert.ok(screen.getAllByText("probe_transport_error").length >= 1);
      assert.ok(screen.getByText("Analysis results"));
      assert.ok(screen.getByText("RAG focus"));
      assert.ok(screen.getByText("Query node"));
      assert.ok(screen.getByText("step retrieval_started · done"));
      assert.ok(screen.getByText("step answer_grounded · done"));
      assert.ok(screen.getByText("Coverage / analysis orb"));
      assert.ok(screen.getByText("Presentation highlights"));
      assert.ok(screen.getByText("Model verdict"));
      assert.ok(screen.getByText("Process telemetry"));
      assert.ok(screen.getByText("trace steps 4"));
      assert.ok(screen.getByText("process steps 7"));
      assert.ok(screen.getByText("Snapshot comparison"));
      assert.ok(screen.getByText("Before"));
      assert.ok(screen.getByText("After"));
      assert.ok(screen.getByText("Delta"));
      assert.ok(screen.getAllByText("Slonce to gwiazda.").length >= 2);
    });

    await waitFor(() => {
      assert.ok(screen.getByText("Graph view"));
      assert.ok(screen.getAllByText("Graph drilldown").length >= 2);
      assert.ok(screen.getAllByText("Relations").length >= 2);
      assert.ok(screen.getAllByText("captum").length >= 2);
    });
  });

  it("toggles normalized and raw token views in logit-lens panel", async () => {
    render(
      <LanguageProvider>
        <ModelIntrospectionMechanismProvider>
          <ModelIntrospectionDashboard />
        </ModelIntrospectionMechanismProvider>
      </LanguageProvider>,
    );

    await waitFor(() => {
      assert.ok(screen.getByRole("button", { name: /Run analysis|Uruchom analizę/i }));
    });
    fireEvent.click(screen.getByRole("button", { name: /Run analysis|Uruchom analizę/i }));

    await waitFor(() => {
      assert.ok(screen.getByText(/Co · to · jest/));
    });
    assert.ok(screen.getAllByText(/attention: recovered via logits proxy/i).length >= 1);
    assert.ok(screen.getAllByText(/saliency: recovered via attention proxy/i).length >= 1);
    assert.equal(screen.queryByText(/▁Co · ▁to · ▁jest/), null);

    fireEvent.click(
      screen.getByLabelText(
        /Przełącz na widok surowy tokenów|Switch to raw token view/i,
      ),
    );
    await waitFor(() => {
      assert.ok(screen.getByText(/▁Co · ▁to · ▁jest/));
    });
  });
});
