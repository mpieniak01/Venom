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
    architecture_graph: makeArchitectureGraphFixture(),
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
    architecture_graph: makeArchitectureGraphFixture(),
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
      layer_internals: {
        source: "probe_runtime",
        status: "ok",
        mode: "probe_runtime",
        summary: {
          layer_count: 1,
          block_count: 3,
          architecture_block_count: 2,
          activation_layer_count: 2,
          activation_transition_count: 1,
          checkpoint_count: 1,
          attention_layer_count: 1,
          saliency_token_count: 3,
          process_step_count: 4,
          timeline_step_count: 7,
        },
        layers: [
          {
            id: "layer_4",
            layer: 4,
            label: "Layer 4",
            status: "changed",
            summary: "checkpoint 25% top token Słońce; attention layer 4; saliency target Słońce",
            state_delta: "Prediction path shifts toward Słońce at checkpoint 25%.",
            blocks: [
              {
                kind: "logit_lens",
                label: "checkpoint 25%",
                summary: "Top token Słońce at checkpoint 25%.",
                detail: "Confidence 0.42; stable token path.",
                impact: "This checkpoint preserves the current prediction path.",
                evidence: ["Słońce (8.125)", "gwiazda (7.750)"],
              },
              {
                kind: "attention",
                label: "attention layer 4",
                summary: "1 head(s) and 1 link(s) reshape the active representation.",
                detail: "Attention exposes the strongest links between the current tokens.",
                impact: "Attention shifts how the layer reads the current context.",
                heads: [
                  {
                    head: 0,
                    summary: "1 link(s)",
                    detail: "Strong attention links from this head.",
                    evidence: ["head 0: Co → Słońce (0.812)"],
                  },
                ],
                evidence: ["head 0: Co → Słońce (0.812)"],
              },
              {
                kind: "saliency",
                label: "saliency target Słońce",
                summary: "Saliency is anchored to Słońce via logits_proxy.",
                detail: "3 weighted token(s) highlight the target path.",
                impact: "Saliency makes the strongest supporting tokens visible.",
                evidence: ["Słońce (0.910)", "gwiazda (0.420)", "to (0.210)"],
              },
            ],
            signals: [
              {
                source: "logit_lens",
                label: "checkpoint 25%",
                detail: "top token Słońce; confidence 0.42; changed no",
                evidence: ["Słońce (8.125)", "gwiazda (7.750)"],
              },
              {
                source: "attention",
                label: "attention layer 4",
                detail: "1 head(s) with 1 link(s)",
                evidence: ["head 0: Co → Słońce (0.812)"],
              },
              {
                source: "saliency",
                label: "saliency target Słońce",
                detail: "method logits_proxy; 3 weighted token(s)",
                evidence: ["Słońce (0.910)", "gwiazda (0.420)", "to (0.210)"],
              },
            ],
            response_linkage: {
              status: "linked",
              layer_id: 4,
              layer_label: "Layer 4",
              coverage_percent: 80,
              fragment_count: 5,
              linked_fragment_count: 4,
              linked_fragments: [
                "Słońce to gwiazda.",
                "Jest to ogromna, gorąca i bardzo jasna kula gazu.",
                "Oto kluczowe informacje o Słońcu.",
              ],
              evidence_links: ["edge:1", "edge:2", "edge:3"],
              dominant_signals: ["checkpoint 25%", "attention layer 4", "saliency target Słońce"],
              summary:
                "4/5 response fragment(s) are evidence-linked. Dominant signals: checkpoint 25%, attention layer 4, saliency target Słońce.",
              impact:
                "This layer's signals align with response fragments that are grounded in evidence.",
              evidence: ["coverage 80.00%", "fragments 4/5", "checkpoint 25%", "attention layer 4"],
            },
            evidence: [
              "checkpoint 25% layer 4: Słońce (0.42)",
              "attention layer 4: 1 head(s)",
              "head 0: Co → Słońce (0.812)",
              "saliency target Słońce via logits_proxy",
            ],
          },
        ],
        architecture_blocks: [
          {
            kind: "mlp",
            label: "Response synthesis",
            summary: "MLP synthesizes hidden state into the residual path.",
            detail: "Source node mlp is the native architecture synthesis block.",
            impact: "This block converts internal state into response-oriented synthesis.",
            evidence: ["enter model", "merge"],
          },
          {
            kind: "residual",
            label: "Reuse path",
            summary: "Residual merge keeps the active path reusable before decode.",
            detail: "Source node residual merges probe and synthesis paths.",
            impact: "Residual flow keeps accumulated state available for the final decode.",
            evidence: ["merge", "decode"],
          },
        ],
        mlp_activation: {
          source: "probe_runtime",
          status: "ok",
          selected_layers: [4],
          mlp_layer: {
            layer: 4,
            label: "Response synthesis",
            role_hint: "mlp",
            hidden_slice: [0.09, -0.15, 0.38, -0.04],
            metrics: {
              mean: 0.07,
              norm: 0.416533,
              max_abs: 0.38,
              top_dimensions: [
                { index: 2, value: 0.38, abs_value: 0.38 },
                { index: 1, value: -0.15, abs_value: 0.15 },
              ],
            },
            summary: "norm 0.417; mean 0.070; top dims 2, 1",
            evidence: ["slice[0]=0.090", "slice len=4"],
          },
          residual_layer: null,
          transition: null,
          tensor_activation: {
            source: "probe_runtime.hidden.hidden_slice",
            status: "ok",
            slice_kind: "hidden_state_slice",
            focus_layer: 4,
            residual_layer: null,
            vector_length: 4,
            mlp_vector: [0.09, -0.15, 0.38, -0.04],
            residual_vector: null,
            delta_vector: null,
            norms: {
              mlp_l2: 0.416533,
              residual_l2: null,
              delta_l2: null,
              cosine_similarity: null,
            },
            top_delta_dimensions: [],
            notes: [
              "Contract exposes hidden-state slice vectors for activation analysis.",
              "This payload is not a full tensor dump of the MLP block.",
            ],
          },
          summary: {
            selected_layer_count: 1,
            focus_layer: 4,
            residual_layer: null,
            hidden_dimension_count: 4,
            max_delta_norm: 0,
            average_norm: 0.416533,
            transition_summary: null,
            transition_impact: null,
          },
          notes: [
            "Source data comes from hidden.hidden_slice for the selected MLP layer.",
            "This is a probe slice, not a full tensor dump.",
          ],
        },
        activation_path: {
          source: "probe_runtime",
          status: "ok",
          selected_layers: [0, 4],
          layers: [
            {
              layer: 0,
              label: "Prompt input",
              role_hint: "input",
              hidden_slice: [0.12, -0.24, 0.31, -0.18],
              metrics: {
                mean: 0.0025,
                norm: 0.4235,
                max_abs: 0.31,
                top_dimensions: [
                  { index: 2, value: 0.31, abs_value: 0.31 },
                  { index: 1, value: -0.24, abs_value: 0.24 },
                ],
              },
              summary: "norm 0.424; mean 0.003; top dims 2, 1",
              evidence: ["slice[0]=0.120", "slice len=4"],
            },
            {
              layer: 4,
              label: "Layer 4",
              role_hint: "layer",
              hidden_slice: [0.18, -0.11, 0.44, -0.07],
              metrics: {
                mean: 0.11,
                norm: 0.495923,
                max_abs: 0.44,
                top_dimensions: [
                  { index: 2, value: 0.44, abs_value: 0.44 },
                  { index: 0, value: 0.18, abs_value: 0.18 },
                ],
              },
              summary: "norm 0.496; mean 0.110; top dims 2, 0",
              evidence: ["slice[0]=0.180", "slice len=4"],
            },
          ],
          transitions: [
            {
              from_layer: 0,
              to_layer: 4,
              before: "Prompt input",
              after: "Layer 4",
              delta_norm: 0.271664,
              mean_shift: 0.1075,
              max_abs_shift: 0.13,
              summary: "Hidden-state delta norm 0.272; mean shift 0.108; peak shift 0.130.",
              impact: "The activation path changes most strongly across this transition.",
              evidence: ["ΔL2 0.272", "Δmean 0.108", "peak |Δ| 0.130"],
            },
          ],
          summary: {
            selected_layer_count: 2,
            transition_count: 1,
            focus_layer: 4,
            max_delta_norm: 0.271664,
            average_norm: 0.459712,
          },
          notes: [
            "Source data comes from hidden.hidden_slice for selected layers.",
            "This is a probe slice, not a full tensor dump.",
          ],
        },
        notes: [
          "Source data comes from logit_lens.checkpoints, attention.layers and saliency.token_weights.",
          "Hidden-state activation path is sourced separately from hidden.hidden_slice.",
          "Process trace steps: 4",
          "Timeline steps: 7",
        ],
      },
      analysis_capabilities: {
        hidden_state: {
          available: true,
          source: "probe_runtime",
          status: "ok",
          reason: "ok",
        },
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
        available_count: 4,
        total_count: 4,
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

function makeStableScreenCompletedPayload() {
  const snapshot = makeSnapshotBeforeFixture();
  const snapshotAfter = makeSnapshotAfterFixture();
  return {
    analysis_enabled: true,
    status: "completed",
    snapshot,
    snapshot_after: snapshotAfter,
    analysis: {
      prompt: "Co to jest slonce?",
      response:
        "Slonce to gwiazda, ktora jest centrum naszego Ukladu Slonecznego i najwazniejszym punktem dla zycia na Ziemi.",
      chunk_count: 1,
      events: ["start", "content", "done"],
      timeline_step_count: 9,
      timeline: [
        { id: "snapshot_before", label: "Snapshot captured", status: "done", detail: snapshot.runtime.label, at_ms: 0, path: "answer_path", progress: 0 },
        { id: "request_ready", label: "Prompt prepared", status: "done", detail: "Co to jest slonce?", at_ms: 184.8, path: "answer_path", progress: 10 },
        { id: "stream_opened", label: "Stream opened", status: "done", detail: "3 event(s) observed", at_ms: 185.5, path: "answer_path", progress: 20 },
        { id: "first_chunk", label: "First content chunk", status: "done", detail: "1 chunk(s) total", at_ms: 12274.1, path: "answer_path", progress: 40 },
        { id: "response_finalized", label: "Response assembled", status: "done", detail: "425 chars", at_ms: 13157.6, path: "answer_path", progress: 85 },
        { id: "internals:logit_lens_probe", label: "Logit lens probe", status: "done", detail: "4 checkpoint(s) · 449.6 ms", at_ms: 13157.6, path: "internals_path", progress: 90 },
        { id: "internals:attention_probe", label: "Attention probe", status: "done", detail: "ok · 286.6 ms", at_ms: 13157.6, path: "internals_path", progress: 93 },
        { id: "internals:saliency_probe", label: "Saliency probe", status: "done", detail: "ok · 83.9 ms", at_ms: 13157.6, path: "internals_path", progress: 96 },
        { id: "snapshot_after", label: "Snapshot refreshed", status: "done", detail: "8 packages available", at_ms: 13354.4, path: "answer_path", progress: 100 },
      ],
      elapsed_ms: 13157.6,
      provider: snapshot.runtime.provider,
      model: snapshot.runtime.model,
      runtime_label: snapshot.runtime.label,
      process: {
        request_id: "53c62b8b-1234-5678-9abc-def012345678",
        status: "COMPLETED",
        step_count: 4,
        trace_step_count: 4,
        steps: [],
        first_chunk_ms: 12088,
        response_chunks: 1,
        response_chars: 425,
        total_ms: 13157.6,
      },
      rag_focus: {
        source: "runtime_trace",
        query: "Co to jest slonce?",
        entities: [{ id: "e1", label: "slonce", kind: "query_token", active: true }],
        evidence_edges: [{ id: "edge:1", from: "query", to: "response:1", label: "context signal", active: true }],
        active_entity_ids: ["e1"],
        grounding_score: 0.9,
        answer_evidence_links: [{ id: "link:1", fragment: "Slonce to gwiazda.", edge_ids: ["edge:1"], entity_ids: ["e1"] }],
      },
      logit_lens: {
        source: "probe_runtime",
        status: "ok",
        code: "logit_lens_proxy",
        message: null,
        runtime_label: snapshot.runtime.label,
        input_tokens: ["Co", "to", "jest", "slonce?"],
        output_tokens: ["Slonce", "to", "gwiazda"],
        raw_input_tokens: ["▁Co", "▁to", "▁jest", "▁s", "ło", "ń", "ce", "?"],
        raw_output_tokens: ["**", "▁Słońce", "▁to", "▁gwiazda"],
        checkpoints: [
          {
            id: "cp_25",
            percent: 25,
            layer: 4,
            top_k: [
              { token: "式", raw_token: "式", token_index: 0, score: 6.094 },
              { token: "<<-", raw_token: "<<-", token_index: 1, score: 6.031 },
            ],
            top_token: "式",
            confidence: 0.22,
            changed: false,
          },
        ],
        signals: { early_unstable: true, late_stabilized: true, low_confidence_path: true },
        interpretability: { interpretable: false, confidence_band: "low", token_noise_ratio: 0, readable_top_tokens: 0, total_top_tokens: 10 },
        diagnostics: { elapsed_ms: 449.6 },
      },
      attention: {
        source: "probe_runtime",
        status: "ok",
        code: "attention_proxy_logits",
        message: "recovered via logits proxy",
        runtime_label: snapshot.runtime.label,
        tokens: ["Co", "to"],
        layers: [{ layer: 0, heads: [{ head: 0, top_links: [{ from_index: 0, to_index: 1, from_token: "?", to_token: "?", weight: 61.75 }] }] }],
        diagnostics: { elapsed_ms: 286.6 },
      },
      saliency: {
        source: "probe_runtime",
        status: "ok",
        code: "saliency_proxy_logits",
        message: "recovered via logits proxy",
        runtime_label: snapshot.runtime.label,
        method: "logits_proxy",
        target_output_token_index: 0,
        target_output_token: "Slonce",
        token_weights: [{ token: "автоматлары", token_index: 0, weight: 42.75 }],
        diagnostics: { elapsed_ms: 83.9 },
      },
      analysis_capabilities: {
        hidden_state: { available: true, source: "probe_runtime", status: "ok", reason: "ok" },
        attention: { available: true, source: "probe_runtime", status: "ok", reason: "attention_proxy_logits" },
        saliency: { available: true, source: "probe_runtime", status: "ok", reason: "saliency_proxy_logits" },
        logit_lens: { available: true, source: "probe_runtime", status: "ok", reason: "ok" },
        available_count: 4,
        total_count: 4,
        probe_profile: "dev",
        probe_enabled: true,
        probe_healthy: true,
        runtime_supported: true,
        endpoint_configured: true,
        model_whitelisted: true,
        limits: { timeout_seconds: 25, max_attempts: 2, max_top_k: 32, max_layer_count: 8, max_head_count: 32, max_prompt_tokens: 1024 },
        internals_verdict: "partial",
      },
      layer_internals: {
        source: "probe_runtime",
        status: "ok",
        mode: "probe_runtime",
        summary: {
          layer_count: 1,
          block_count: 3,
          architecture_block_count: 2,
          activation_layer_count: 2,
          activation_transition_count: 1,
          checkpoint_count: 1,
          attention_layer_count: 1,
          saliency_token_count: 1,
          process_step_count: 4,
          timeline_step_count: 9,
        },
        layers: [
          {
            id: "layer_4",
            layer: 4,
            label: "Layer 4",
            status: "inspection",
            summary: "checkpoint 25% top token Słońce; attention layer 0; saliency target Slonce",
            state_delta: "Prediction path stays centered on Słońce at checkpoint 25%.",
            blocks: [
              {
                kind: "logit_lens",
                label: "checkpoint 25%",
                summary: "Top token Słońce at checkpoint 25%.",
                detail: "Confidence 0.22; stable token path.",
                impact: "This checkpoint preserves the current prediction path.",
                evidence: ["式 (6.094)", "<<- (6.031)"],
              },
              {
                kind: "attention",
                label: "attention layer 0",
                summary: "1 head(s) and 1 link(s) reshape the active representation.",
                detail: "Attention exposes the strongest links between the current tokens.",
                impact: "Attention shifts how the layer reads the current context.",
                heads: [
                  {
                    head: 0,
                    summary: "1 link(s)",
                    detail: "Strong attention links from this head.",
                    evidence: ["head 0: ? → ? (61.750)"],
                  },
                ],
                evidence: ["head 0: ? → ? (61.750)"],
              },
              {
                kind: "saliency",
                label: "saliency target Slonce",
                summary: "Saliency is anchored to Slonce via logits_proxy.",
                detail: "1 weighted token(s) highlight the target path.",
                impact: "Saliency makes the strongest supporting tokens visible.",
                evidence: ["автоматлары (42.750)"],
              },
            ],
            signals: [
              {
                source: "logit_lens",
                label: "checkpoint 25%",
                detail: "top token Słońce; confidence 0.22; changed no",
                evidence: ["式 (6.094)", "<<- (6.031)"],
              },
              {
                source: "attention",
                label: "attention layer 0",
                detail: "1 head(s) with 1 link(s)",
                evidence: ["head 0: ? → ? (61.750)"],
              },
              {
                source: "saliency",
                label: "saliency target Slonce",
                detail: "method logits_proxy; 1 weighted token(s)",
                evidence: ["автоматлары (42.750)"],
              },
            ],
            response_linkage: {
              status: "linked",
              layer_id: 4,
              layer_label: "Layer 4",
              coverage_percent: 66.67,
              fragment_count: 3,
              linked_fragment_count: 2,
              linked_fragments: [
                "Słońce to gwiazda.",
                "Jest to ogromna, gorąca i bardzo jasna kula gazu.",
              ],
              evidence_links: ["edge:1", "edge:2"],
              dominant_signals: ["checkpoint 25%", "attention layer 0", "saliency target Slonce"],
              summary:
                "2/3 response fragment(s) are evidence-linked. Dominant signals: checkpoint 25%, attention layer 0, saliency target Slonce.",
              impact:
                "This layer's signals align with response fragments that are grounded in evidence.",
              evidence: ["coverage 66.67%", "fragments 2/3", "checkpoint 25%", "attention layer 0"],
            },
            evidence: [
              "checkpoint 25% layer 4: 式 (0.22)",
              "attention layer 0: 1 head(s)",
              "head 0: ? → ? (61.750)",
              "saliency target Slonce via logits_proxy",
            ],
          },
        ],
        architecture_blocks: [
          {
            kind: "mlp",
            label: "Response synthesis",
            summary: "MLP synthesizes hidden state into the residual path.",
            detail: "Source node mlp is the native architecture synthesis block.",
            impact: "This block converts internal state into response-oriented synthesis.",
            evidence: ["synthesis path", "merge"],
          },
          {
            kind: "residual",
            label: "Reuse path",
            summary: "Residual merge keeps the active path reusable before decode.",
            detail: "Source node residual merges probe and synthesis paths.",
            impact: "Residual flow keeps accumulated state available for the final decode.",
            evidence: ["merge", "decode"],
          },
        ],
        mlp_activation: {
          source: "probe_runtime",
          status: "ok",
          selected_layers: [4],
          mlp_layer: {
            layer: 4,
            label: "Response synthesis",
            role_hint: "mlp",
            hidden_slice: [0.09, -0.15, 0.38, -0.04],
            metrics: {
              mean: 0.07,
              norm: 0.416533,
              max_abs: 0.38,
              top_dimensions: [
                { index: 2, value: 0.38, abs_value: 0.38 },
                { index: 1, value: -0.15, abs_value: 0.15 },
              ],
            },
            summary: "norm 0.417; mean 0.070; top dims 2, 1",
            evidence: ["slice[0]=0.090", "slice len=4"],
          },
          residual_layer: null,
          transition: null,
          tensor_activation: {
            source: "probe_runtime.hidden.hidden_slice",
            status: "ok",
            slice_kind: "hidden_state_slice",
            focus_layer: 4,
            residual_layer: null,
            vector_length: 4,
            mlp_vector: [0.09, -0.15, 0.38, -0.04],
            residual_vector: null,
            delta_vector: null,
            norms: {
              mlp_l2: 0.416533,
              residual_l2: null,
              delta_l2: null,
              cosine_similarity: null,
            },
            top_delta_dimensions: [],
            notes: [
              "Contract exposes hidden-state slice vectors for activation analysis.",
              "This payload is not a full tensor dump of the MLP block.",
            ],
          },
          summary: {
            selected_layer_count: 1,
            focus_layer: 4,
            residual_layer: null,
            hidden_dimension_count: 4,
            max_delta_norm: 0,
            average_norm: 0.416533,
            transition_summary: null,
            transition_impact: null,
          },
          notes: [
            "Source data comes from hidden.hidden_slice for the selected MLP layer.",
            "This is a probe slice, not a full tensor dump.",
          ],
        },
        activation_path: {
          source: "probe_runtime",
          status: "ok",
          selected_layers: [0, 4],
          layers: [
            {
              layer: 0,
              label: "Prompt input",
              role_hint: "input",
              hidden_slice: [0.12, -0.24, 0.31, -0.18],
              metrics: {
                mean: 0.0025,
                norm: 0.4235,
                max_abs: 0.31,
                top_dimensions: [
                  { index: 2, value: 0.31, abs_value: 0.31 },
                  { index: 1, value: -0.24, abs_value: 0.24 },
                ],
              },
              summary: "norm 0.424; mean 0.003; top dims 2, 1",
              evidence: ["slice[0]=0.120", "slice len=4"],
            },
            {
              layer: 4,
              label: "Layer 4",
              role_hint: "layer",
              hidden_slice: [0.18, -0.11, 0.44, -0.07],
              metrics: {
                mean: 0.11,
                norm: 0.495923,
                max_abs: 0.44,
                top_dimensions: [
                  { index: 2, value: 0.44, abs_value: 0.44 },
                  { index: 0, value: 0.18, abs_value: 0.18 },
                ],
              },
              summary: "norm 0.496; mean 0.110; top dims 2, 0",
              evidence: ["slice[0]=0.180", "slice len=4"],
            },
          ],
          transitions: [
            {
              from_layer: 0,
              to_layer: 4,
              before: "Prompt input",
              after: "Layer 4",
              delta_norm: 0.271664,
              mean_shift: 0.1075,
              max_abs_shift: 0.13,
              summary: "Hidden-state delta norm 0.272; mean shift 0.108; peak shift 0.130.",
              impact: "The activation path changes most strongly across this transition.",
              evidence: ["ΔL2 0.272", "Δmean 0.108", "peak |Δ| 0.130"],
            },
          ],
          summary: {
            selected_layer_count: 2,
            transition_count: 1,
            focus_layer: 4,
            max_delta_norm: 0.271664,
            average_norm: 0.459712,
          },
          notes: [
            "Source data comes from hidden.hidden_slice for selected layers.",
            "This is a probe slice, not a full tensor dump.",
          ],
        },
        notes: [
          "Source data comes from logit_lens.checkpoints, attention.layers and saliency.token_weights.",
          "Hidden-state activation path is sourced separately from hidden.hidden_slice.",
          "Process trace steps: 4",
          "Timeline steps: 9",
        ],
      },
    },
  };
}

function createStableScreenStreamingResponse() {
  const encoder = new TextEncoder();
  const donePayload = makeStableScreenCompletedPayload();
  const events = [
    { delayMs: 0, payload: `event: analysis_start\ndata: ${JSON.stringify(makeAnalysisRunningPayload())}\n\n` },
    { delayMs: 0, payload: "event: start\ndata: {}\n\n" },
    { delayMs: 0, payload: 'event: content\ndata: {"text":"Slonce to gwiazda."}\n\n' },
    { delayMs: 0, payload: "event: done\ndata: {}\n\n" },
    { delayMs: 0, payload: `event: analysis_done\ndata: ${JSON.stringify(donePayload)}\n\n` },
  ];
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const event of events) {
          controller.enqueue(encoder.encode(event.payload));
        }
        controller.close();
      },
    }),
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
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
    assert.ok(screen.getByRole("link", { name: "Open Knowledge Graph" }));
    assert.ok(screen.getByLabelText("Prompt"));
    assert.equal(screen.queryByText("Graph view"), null);

    fireEvent.click(
      screen.getByRole("button", {
        name: /Refresh snapshot|Odśwież migawkę/i,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Run analysis" }));

    await waitFor(() => {
      assert.ok(screen.getByText("Snapshot captured"));
      assert.ok(screen.getByText("Prompt prepared"));
      assert.ok(screen.getByText("First content chunk"));
      assert.ok(
        screen.getByText(/przetwarzanie internals|internals processing/i),
      );
      assert.ok(
        screen.getAllByText(/materializacja kroku|step materialization/i).length >= 1,
      );
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
      assert.ok(screen.getByText("trace steps 7"));
      assert.ok(screen.getByText("process steps 7"));
      assert.ok(screen.getByText("Snapshot comparison"));
      assert.ok(screen.getByText("Before"));
      assert.ok(screen.getByText("After"));
      assert.ok(screen.getByText("Delta"));
      assert.ok(screen.getAllByText("Slonce to gwiazda.").length >= 1);
    });
  });

  it("renders architecture graph when snapshot includes architecture payload", async () => {
    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      if (!url.includes("/api/v1/models/introspection")) {
        throw new Error(`Unexpected fetch URL: ${url}`);
      }
      if (url.includes("/api/v1/models/introspection/analyze/stream")) {
        return createStreamingAnalysisResponse();
      }
      return new Response(
        JSON.stringify({
          success: true,
          snapshot: {
            ...makeSnapshotBeforeFixture(),
            architecture_graph: makeArchitectureGraphFixture(),
          },
        }),
        { status: 200 },
      );
    };

    render(
      <LanguageProvider>
        <ModelIntrospectionMechanismProvider>
          <ModelIntrospectionDashboard />
        </ModelIntrospectionMechanismProvider>
      </LanguageProvider>,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /Refresh snapshot|Odśwież migawkę/i,
      }),
    );

    await waitFor(() => {
      assert.ok(screen.getByRole("heading", { name: /Architecture graph|Graf architektury/i }));
    });
    assert.ok(screen.getByTestId("architecture-graph-container"));
    assert.ok(screen.getByText("Architecture drilldown"));
    assert.ok(screen.getByText(/Architecture overview|Przegląd architektury/i));
    assert.ok(screen.getByText(/Important transitions|Ważne przejścia/i));
    assert.ok(screen.getByText(/Progress checkpoints|Punkty kontrolne przebiegu/i));
    assert.ok(screen.getByText(/Layer internals|Wnętrze warstwy/i));
    assert.ok(screen.getAllByText(/Activation path|activation path/i).length >= 1);
    assert.ok(screen.getAllByText(/transformer block 1/i).length >= 1);
    assert.ok(screen.getByText(/Transition detail|Szczegóły przejścia/i));
    assert.ok(screen.getByText(/Final outcome|Wynik końcowy/i));
    assert.ok(screen.getAllByText(/Supporting signals|Sygnały wspierające/i).length >= 1);
    assert.ok(screen.getAllByText(/Before|Przed/i).length >= 1);
    assert.ok(screen.getAllByText(/After|Po/i).length >= 1);
    assert.ok(screen.getAllByText(/Delta|Wpływ/i).length >= 1);
    assert.ok(screen.getByText("ready available"));
    assert.ok(screen.getByText("fidelity native"));
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

  it("keeps stable-screen contract from PR230 without regressions", async () => {
    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      if (!url.includes("/api/v1/models/introspection")) {
        throw new Error(`Unexpected fetch URL: ${url}`);
      }
      if (url.includes("/api/v1/models/introspection/analyze/stream")) {
        return createStableScreenStreamingResponse();
      }
      return new Response(JSON.stringify({ success: true, snapshot: makeSnapshotBeforeFixture() }), {
        status: 200,
      });
    };

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
      assert.ok(screen.getByText("1 chunk(s) · 9 step(s) · completed"));
      assert.ok(screen.getAllByText(/Advanced internals/i).length >= 1);
      assert.ok(screen.getAllByText(/internals partial/i).length >= 1);
      assert.ok(screen.getAllByText(/coverage 4\/4/i).length >= 1);
      assert.ok(screen.getAllByText(/attention: recovered via logits proxy/i).length >= 1);
      assert.ok(screen.getAllByText(/saliency: recovered via logits proxy/i).length >= 1);
      assert.ok(screen.getByText(/token flow/i));
      assert.ok(screen.getAllByText(/Progress checkpoints|Punkty kontrolne przebiegu/i).length >= 1);
      assert.ok(screen.getAllByText(/Layer internals|Wnętrze warstwy/i).length >= 1);
      assert.ok(screen.getAllByText(/Dominant signals|Dominujące sygnały/i).length >= 1);
      assert.ok(screen.getAllByText(/Activation path|activation path/i).length >= 1);
      assert.ok(screen.getAllByText(/Response linkage|Powiązanie z odpowiedzią/i).length >= 1);
      assert.ok(screen.getAllByText(/State delta|Delta stanu/i).length >= 1);
      assert.ok(screen.getAllByText(/blocks|bloków/i).length >= 1);
      assert.ok(screen.getAllByText(/architecture blocks|bloków architektury/i).length >= 1);
      assert.ok(screen.getAllByText(/Heads|Głowy/i).length >= 1);
      assert.ok(screen.getAllByText(/Signals|Sygnały/i).length >= 1);
      assert.ok(screen.getByText(/25% · layer 4/i));
      assert.ok(screen.getAllByText(/Logit lens probe/i).length >= 1);
      assert.ok(screen.getAllByText(/Attention probe/i).length >= 1);
      assert.ok(screen.getAllByText(/Saliency probe/i).length >= 1);
      assert.equal(screen.queryByText(/Ukryj advanced internals/i), null);
      assert.equal(screen.queryByText(/Pokaż advanced internals/i), null);
    });

    await waitFor(() => {
      const resultsPanel = screen.getByText("Analysis results").closest("section");
      assert.ok(resultsPanel);
      const content = resultsPanel.textContent ?? "";
      const step2 = content.indexOf("step 2 · Prompt prepared");
      const step5 = content.indexOf("step 5 · Response assembled");
      const step6 = content.indexOf("step 6 · Snapshot refreshed");
      const step7 = content.indexOf("step 7 · Logit lens probe");
      const step8 = content.indexOf("step 8 · Attention probe");
      const step9 = content.indexOf("step 9 · Saliency probe");
      assert.ok(step2 >= 0);
      assert.ok(step5 >= 0);
      assert.ok(step6 >= 0);
      assert.ok(step7 >= 0);
      assert.ok(step8 >= 0);
      assert.ok(step9 >= 0);
      assert.ok(step2 < step5);
      assert.ok(step7 < step8);
      assert.ok(step8 < step9);
    });
  });

  it("shows lite internals guidance for ollama runtime", async () => {
    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = String(input);
      if (!url.includes("/api/v1/models/introspection")) {
        throw new Error(`Unexpected fetch URL: ${url}`);
      }
      if (url.includes("/api/v1/models/introspection/analyze/stream")) {
        const snapshot = {
          ...makeSnapshotBeforeFixture(),
          runtime: {
            ...makeSnapshotBeforeFixture().runtime,
            provider: "ollama",
            model: "gemma3:latest",
            endpoint: "http://localhost:11434/v1",
            label: "gemma3:latest · ollama @ localhost:11434",
          },
          summary: {
            ...makeSnapshotBeforeFixture().summary,
            provider: "ollama",
            runtime_label: "gemma3:latest · ollama @ localhost:11434",
            introspection_level: "lite",
          },
          introspection_level: "lite",
        };
        const donePayload = {
          analysis_enabled: true,
          status: "completed",
          snapshot,
          snapshot_after: snapshot,
          analysis: {
            prompt: "Co to jest slonce?",
            response: "Słońce to gwiazda.",
            chunk_count: 1,
            events: ["start", "content", "done"],
            timeline_step_count: 9,
            timeline: [
              { id: "snapshot_before", label: "Snapshot captured", status: "done", detail: snapshot.runtime.label, at_ms: 0, path: "answer_path", progress: 0 },
              { id: "request_ready", label: "Prompt prepared", status: "done", detail: "Co to jest slonce?", at_ms: 10, path: "answer_path", progress: 10 },
              { id: "stream_opened", label: "Stream opened", status: "done", detail: "3 event(s) observed", at_ms: 20, path: "answer_path", progress: 20 },
              { id: "first_chunk", label: "First content chunk", status: "done", detail: "1 chunk(s) total", at_ms: 30, path: "answer_path", progress: 40 },
              { id: "response_finalized", label: "Response assembled", status: "done", detail: "18 chars", at_ms: 40, path: "answer_path", progress: 85 },
              { id: "internals:logit_lens_probe", label: "Logit lens probe", status: "done", detail: "4 checkpoint(s)", at_ms: 50, path: "internals_path", progress: 90 },
              { id: "internals:attention_probe", label: "Attention probe", status: "skipped", detail: "not available", at_ms: 50, path: "internals_path", progress: 93 },
              { id: "internals:saliency_probe", label: "Saliency probe", status: "skipped", detail: "not available", at_ms: 50, path: "internals_path", progress: 96 },
              { id: "snapshot_after", label: "Snapshot refreshed", status: "done", detail: "8 packages available", at_ms: 60, path: "answer_path", progress: 100 },
            ],
            elapsed_ms: 60,
            provider: "ollama",
            model: "gemma3:latest",
            runtime_label: snapshot.runtime.label,
            logit_lens: {
              source: "probe_lite",
              status: "ok",
              code: "ollama_logprobs_lite",
              message: "Token-level logprobs from ollama",
              runtime_label: snapshot.runtime.label,
              input_tokens: ["Co", "to", "jest"],
              output_tokens: ["Słońce", "to", "gwiazda"],
              raw_input_tokens: ["Co", "to", "jest"],
              raw_output_tokens: ["Słońce", "to", "gwiazda"],
              checkpoints: [{ id: "cp_0", percent: 0, layer: -1, top_k: [{ token: "Słońce", token_index: 0, score: -0.1 }], top_token: "Słońce", confidence: 0.9, changed: false }],
              signals: { early_unstable: false, late_stabilized: true, low_confidence_path: false },
              interpretability: { interpretable: true, confidence_band: "high", token_noise_ratio: 0.1, readable_top_tokens: 1, total_top_tokens: 1 },
              diagnostics: {},
            },
            attention: { source: "probe_unavailable", status: "probe_unavailable", code: "runtime_not_supported", message: "not available", layers: [] },
            saliency: { source: "probe_unavailable", status: "probe_unavailable", code: "runtime_not_supported", message: "not available", token_weights: [] },
            analysis_capabilities: {
              hidden_state: { available: false, source: "probe_unavailable", status: "probe_unavailable", reason: "runtime_not_supported", availability_class: "unavailable" },
              attention: { available: false, source: "probe_unavailable", status: "probe_unavailable", reason: "runtime_not_supported", availability_class: "unavailable" },
              saliency: { available: false, source: "probe_unavailable", status: "probe_unavailable", reason: "runtime_not_supported", availability_class: "unavailable" },
              logit_lens: { available: true, source: "probe_lite", status: "ok", reason: "ollama_logprobs_lite", availability_class: "proxy_ok" },
              available_count: 1,
              total_count: 4,
              probe_profile: "legacy_text_only",
              probe_enabled: false,
              probe_healthy: false,
              probe_status: "disabled",
              runtime_supported: false,
              endpoint_configured: true,
              model_whitelisted: false,
              limits: { timeout_seconds: 20, max_attempts: 2, max_top_k: 32, max_layer_count: 8, max_head_count: 32, max_prompt_tokens: 1024 },
              internals_verdict: "partial",
              introspection_level: "lite",
            },
            introspection_level: "lite",
          },
        };
        const encoder = new TextEncoder();
        const events = [
          `event: analysis_start\ndata: ${JSON.stringify(makeAnalysisRunningPayload())}\n\n`,
          "event: start\ndata: {}\n\n",
          'event: content\ndata: {"text":"Słońce to gwiazda."}\n\n',
          "event: done\ndata: {}\n\n",
          `event: analysis_done\ndata: ${JSON.stringify(donePayload)}\n\n`,
        ];
        return new Response(
          new ReadableStream({
            start(controller) {
              for (const event of events) controller.enqueue(encoder.encode(event));
              controller.close();
            },
          }),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        );
      }
      return new Response(JSON.stringify({ success: true, snapshot: makeSnapshotBeforeFixture() }), {
        status: 200,
      });
    };

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
      assert.ok(screen.getByText(/Token confidence \(lite\)/i));
      assert.ok(screen.getByText(/How to get full internals|jak uzyskać pełne internals/i));
      assert.ok(screen.getByText(/Switch runtime to multi_runtime/i));
    });
  });
});
