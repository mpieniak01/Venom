import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildOperatorConclusion,
  buildOperatorRunbookSteps,
  buildLogitLensModel,
  buildRagFocusModel,
  computeAnalysisProgress,
  getFallbackSignalTone,
  getOperatorFinalStatusTone,
  getOperatorStreamModeTone,
  getRagGroundingTone,
  getAnalysisPhase,
  getAnswerStatusLabel,
  getAnswerTone,
  timelineBadgeTone,
  resolveFallbackSignal,
  resolveOperatorFinalStatus,
  resolveOperatorStreamMode,
  splitAnswerHighlights,
} from "../components/inspector/model-introspection-dashboard-view-model";

describe("model introspection dashboard view-model", () => {
  it("computes waiting progress for running analysis before first chunk", () => {
    const progress = computeAnalysisProgress({
      analysisVisible: true,
      analysisTimelineProgress: 0,
      analysisStepCount: 3,
      chunkCount: 0,
      firstChunkMs: null,
      elapsedMs: 5000,
      analysisStatus: "running",
    });
    assert.ok(progress >= 30);
    assert.ok(progress <= 100);
  });

  it("returns zero progress when analysis is not visible", () => {
    const progress = computeAnalysisProgress({
      analysisVisible: false,
      analysisTimelineProgress: 20,
      analysisStepCount: 3,
      chunkCount: 0,
      firstChunkMs: null,
      elapsedMs: 1000,
      analysisStatus: "idle",
    });
    assert.equal(progress, 0);
  });

  it("maps phase to completed when timeline finalized", () => {
    const phase = getAnalysisPhase({
      analysisVisible: true,
      analysisLoading: false,
      analysisStatus: "running",
      timelineHasResponseFinalized: true,
      firstChunkMs: 10,
      chunkCount: 1,
    });
    assert.equal(phase, "completed");
  });

  it("returns warning tone for contextual answers", () => {
    const tone = getAnswerTone("Potrzebuję więcej kontekstu.", true);
    assert.equal(tone, "warning");
  });

  it("returns streaming answer label for running result without text", () => {
    const label = getAnswerStatusLabel({
      response: "",
      analysisRunning: true,
      answeredLabel: "model answered",
      streamingLabel: "streaming answer",
      awaitingLabel: "awaiting answer",
    });
    assert.equal(label, "streaming answer");
  });

  it("splits answer highlights into short list", () => {
    const highlights = splitAnswerHighlights(
      "Pierwsze zdanie. Drugie zdanie. Trzecie zdanie. Czwarte zdanie. Piąte zdanie.",
    );
    assert.equal(highlights.length, 4);
  });

  it("maps completed analysis to operator final status", () => {
    const status = resolveOperatorFinalStatus({
      analysisStatus: "completed",
      analysisVisible: true,
    });
    assert.equal(status, "completed");
    assert.equal(getOperatorFinalStatusTone(status), "success");
  });

  it("detects delayed single chunk stream mode", () => {
    const mode = resolveOperatorStreamMode({
      analysisVisible: true,
      chunkCount: 1,
      firstChunkMs: 2500,
    });
    assert.equal(mode, "single_chunk_delayed");
    assert.equal(getOperatorStreamModeTone(mode), "warning");
  });

  it("detects fallback usage from adapter metadata", () => {
    const signal = resolveFallbackSignal({
      adapterApplied: true,
      adapterId: "demo-adapter",
    });
    assert.equal(signal, "used");
    assert.equal(getFallbackSignalTone(signal), "warning");
  });

  it("builds rag focus model from fallback graph data", () => {
    const ragFocus = buildRagFocusModel({
      analysisPrompt: "Co to jest słońce?",
      analysisStatus: "completed",
      chunkCount: 1,
      analysisTimeline: [
        { id: "request_ready", label: "Prompt prepared", status: "done", detail: "", at_ms: 1 },
        { id: "stream_opened", label: "Stream opened", status: "done", detail: "", at_ms: 2 },
        { id: "response_finalized", label: "Response assembled", status: "done", detail: "", at_ms: 3 },
      ],
      analysisProcess: {
        request_id: "req-1",
        status: "COMPLETED",
        step_count: 1,
        steps: [{ component: "SimpleMode", action: "context_preview", status: "ok", details: "{}" }],
        context_preview_truncated: false,
      },
      snapshot: {
        runtime: {
          provider: "multi_runtime",
          model: "gemma",
          endpoint: "http://localhost:8014/v1",
          service_type: "local",
          mode: "LOCAL",
          label: "gemma · multi_runtime",
          config_hash: "abc",
          runtime_id: "runtime-1",
        },
        runtime_drift: {
          drift_detected: false,
          active_server: "multi_runtime",
          inferred_provider: "multi_runtime",
          model_name: "gemma",
          endpoint: "http://localhost:8014/v1",
          issues: [],
        },
        packages: {},
        available_packages: [],
        missing_packages: [],
        model_manager: { available: true, usage_metrics: null, error: null },
        reuse: {
          brain: { path: "/brain", available: true, purpose: "graph" },
          diagnostics: [],
        },
        summary: {
          active_model: "gemma",
          provider: "multi_runtime",
          runtime_label: "gemma · multi_runtime",
          introspection_ready: true,
        },
        graph: {
          nodes: [
            { id: "runtime", label: "runtime", kind: "runtime", status: "ok" },
            { id: "analysis", label: "analysis", kind: "analysis", status: "ok" },
            { id: "brain", label: "brain", kind: "reuse", status: "available" },
          ],
          edges: [{ from: "analysis", to: "brain", label: "uses" }],
          summary: {
            nodes: 3,
            edges: 1,
            available_packages: 0,
            missing_packages: 0,
            drift_issues: 0,
          },
        },
      },
      ragFocusPayload: null,
    });
    assert.ok(ragFocus);
    assert.equal(ragFocus?.source, "graph_fallback");
    assert.equal(ragFocus?.entities.length, 2);
    assert.equal(ragFocus?.evidenceEdges.length, 1);
    assert.ok((ragFocus?.evidenceEdges[0]?.id ?? "").startsWith("edge:"));
    assert.equal(ragFocus?.answerEvidenceLinks.length, 0);
    assert.equal(ragFocus?.steps.length, 4);
    assert.equal(getRagGroundingTone(ragFocus?.grounding ?? "unknown"), "warning");
  });

  it("builds logit-lens model from payload", () => {
    const logitLens = buildLogitLensModel({
      status: "ok",
      code: null,
      message: null,
      runtime_label: "gemma · multi_runtime",
      input_tokens: ["▁Co", "▁to", "▁jest"],
      output_tokens: ["▁Słońce", "▁to"],
      checkpoints: [
        {
          id: "cp_25",
          percent: 25,
          layer: 8,
          top_k: [
            { token: "▁planeta", token_index: 1, score: 1.1 },
            { token: "▁gwiazda", token_index: 2, score: 1.0 },
          ],
          top_token: "▁planeta",
          confidence: 0.31,
          changed: false,
        },
      ],
      signals: {
        early_unstable: true,
        late_stabilized: false,
        low_confidence_path: true,
      },
      interpretability: {
        interpretable: false,
        confidence_band: "low",
        token_noise_ratio: 0.75,
        readable_top_tokens: 1,
        total_top_tokens: 4,
      },
      diagnostics: { elapsed_ms: 11.2 },
    });

    assert.ok(logitLens);
    assert.equal(logitLens?.source, "probe_unavailable");
    assert.equal(logitLens?.input_tokens[0], "Co");
    assert.equal(logitLens?.raw_input_tokens[0], "▁Co");
    assert.equal(logitLens?.checkpoints.length, 1);
    assert.equal(logitLens?.checkpoints[0]?.top_k[0]?.token, "planeta");
    assert.equal(logitLens?.checkpoints[0]?.top_k[0]?.raw_token, "▁planeta");
    assert.equal(logitLens?.signals.low_confidence_path, true);
  });

  it("builds operator conclusion for grounded runtime signal", () => {
    const conclusion = buildOperatorConclusion({
      analysisVisible: true,
      analysisStatus: "completed",
      ragFocus: {
        source: "runtime_trace",
        query: "Co to jest słońce?",
        entities: [{ id: "e1", label: "Słońce", kind: "entity", active: true }],
        evidenceEdges: [{ id: "edge:1", from: "query", to: "e1", label: "grounded", active: true }],
        answerEvidenceLinks: [
          { id: "link:1", fragment: "Słońce to gwiazda.", edgeIds: ["edge:1"], entityIds: ["e1"] },
        ],
        activeEntityIds: ["e1"],
        grounding: "strong",
        steps: [
          { id: "retrieval_started", status: "done" },
          { id: "entities_linked", status: "done" },
          { id: "context_packed", status: "done" },
          { id: "answer_grounded", status: "done" },
        ],
      },
      logitLens: {
        source: "probe_runtime",
        status: "ok",
        code: null,
        message: null,
        runtime_label: "gemma · multi_runtime",
        input_tokens: [],
        output_tokens: [],
        raw_input_tokens: [],
        raw_output_tokens: [],
        checkpoints: [],
        signals: {
          early_unstable: false,
          late_stabilized: true,
          low_confidence_path: false,
        },
        interpretability: {
          interpretable: true,
          confidence_band: "high",
          token_noise_ratio: 0.1,
          readable_top_tokens: 4,
          total_top_tokens: 4,
        },
        diagnostics: {},
      },
    });
    assert.ok(conclusion);
    assert.equal(conclusion?.verdict, "grounded");
    assert.equal(conclusion?.tone, "success");
    assert.equal(conclusion?.partial, false);
  });

  it("maps skipped model drift to dedicated operator reason code", () => {
    const conclusion = buildOperatorConclusion({
      analysisVisible: true,
      analysisStatus: "skipped",
      skippedReason: "model_drift_detected",
      analysisErrorCode: "MODEL_DRIFT_DETECTED",
      ragFocus: null,
      logitLens: null,
    });

    assert.ok(conclusion);
    assert.equal(conclusion?.verdict, "ungrounded");
    assert.equal(conclusion?.reasonCodes[0], "R0_MODEL_DRIFT");
    assert.equal(conclusion?.reasons[0], "model drift detected");
  });

  it("maps degraded endpoint skip to dedicated operator reason code", () => {
    const conclusion = buildOperatorConclusion({
      analysisVisible: true,
      analysisStatus: "skipped",
      skippedReason: "traffic_control_degraded_mode",
      analysisErrorCode: "DEGRADED_ENDPOINT_UNREACHABLE",
      ragFocus: null,
      logitLens: null,
    });

    assert.ok(conclusion);
    assert.equal(conclusion?.reasonCodes[0], "R0_DEGRADED_ENDPOINT");
    assert.equal(conclusion?.reasons[0], "degraded mode: endpoint unreachable");
  });

  it("builds runbook steps for model drift", () => {
    const steps = buildOperatorRunbookSteps(["R0_MODEL_DRIFT"]);
    assert.equal(steps.length, 3);
    assert.equal(
      steps[0],
      "inspector.modelIntrospection.dashboard.results.runbook.modelDrift.step1",
    );
  });

  it("builds runbook steps for degraded endpoint", () => {
    const steps = buildOperatorRunbookSteps(["R0_DEGRADED_ENDPOINT"]);
    assert.equal(steps.length, 3);
    assert.equal(
      steps[0],
      "inspector.modelIntrospection.dashboard.results.runbook.degradedEndpoint.step1",
    );
  });

  it("builds runbook steps for probe fallback", () => {
    const steps = buildOperatorRunbookSteps(["R3_PROBE_FALLBACK"]);
    assert.equal(steps.length, 3);
    assert.equal(
      steps[0],
      "inspector.modelIntrospection.dashboard.results.runbook.probeFallback.step1",
    );
  });

  it("builds runbook steps for probe proxy", () => {
    const steps = buildOperatorRunbookSteps(["R3_PROBE_PROXY"]);
    assert.equal(steps.length, 3);
    assert.equal(
      steps[0],
      "inspector.modelIntrospection.dashboard.results.runbook.probeFallback.step1",
    );
  });

  it("builds runbook steps for probe failed", () => {
    const steps = buildOperatorRunbookSteps(["R3_PROBE_FAILED"]);
    assert.equal(steps.length, 3);
    assert.equal(
      steps[0],
      "inspector.modelIntrospection.dashboard.results.runbook.probeFallback.step1",
    );
  });

  it("builds runbook steps for delayed stream", () => {
    const steps = buildOperatorRunbookSteps(["R4_STREAM_DELAYED"]);
    assert.equal(steps.length, 3);
    assert.equal(
      steps[0],
      "inspector.modelIntrospection.dashboard.results.runbook.streamDelayed.step1",
    );
  });

  it("builds runbook steps for high logit noise", () => {
    const steps = buildOperatorRunbookSteps(["R5_LOGIT_NOISE_HIGH"]);
    assert.equal(steps.length, 3);
    assert.equal(
      steps[0],
      "inspector.modelIntrospection.dashboard.results.runbook.logitNoiseHigh.step1",
    );
  });

  it("maps failed timeline status to danger tone", () => {
    assert.equal(timelineBadgeTone("failed"), "danger");
  });

  it("maps failed internals timeline to probe failed operator reason", () => {
    const conclusion = buildOperatorConclusion({
      analysisVisible: true,
      analysisStatus: "completed",
      analysisTimeline: [
        {
          id: "internals:logit_lens_probe",
          label: "Logit lens probe",
          progress: 90,
          status: "failed",
          at_ms: 120,
          detail: "probe_failed",
          reason_code: "probe_failed",
        },
      ],
      ragFocus: {
        source: "runtime_trace",
        query: "Co to jest słońce?",
        entities: [{ id: "e1", label: "Słońce", kind: "entity", active: true }],
        evidenceEdges: [{ id: "edge:1", from: "query", to: "e1", label: "grounded", active: true }],
        answerEvidenceLinks: [
          { id: "link:1", fragment: "Słońce to gwiazda.", edgeIds: ["edge:1"], entityIds: ["e1"] },
        ],
        activeEntityIds: ["e1"],
        grounding: "strong",
        steps: [
          { id: "retrieval_started", status: "done" },
          { id: "entities_linked", status: "done" },
          { id: "context_packed", status: "done" },
          { id: "answer_grounded", status: "done" },
        ],
      },
      logitLens: {
        source: "probe_unavailable",
        status: "probe_unavailable",
        code: "probe_failed",
        message: null,
        runtime_label: "gemma · multi_runtime",
        input_tokens: [],
        output_tokens: [],
        raw_input_tokens: [],
        raw_output_tokens: [],
        checkpoints: [],
        signals: {
          early_unstable: false,
          late_stabilized: false,
          low_confidence_path: true,
        },
        interpretability: {
          interpretable: false,
          confidence_band: "low",
          token_noise_ratio: 0.9,
          readable_top_tokens: 0,
          total_top_tokens: 0,
        },
        diagnostics: {},
      },
    });
    assert.ok(conclusion);
    assert.equal(conclusion?.reasonCodes.includes("R3_PROBE_FAILED"), true);
  });
});
