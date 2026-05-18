"use client";

export type PackageProbe = {
  module: string;
  package: string;
  available: boolean;
  version: string | null;
};

export type IntrospectionSnapshot = {
  runtime: {
    provider: string;
    model: string;
    endpoint: string | null;
    service_type: string;
    mode: string;
    label: string;
    config_hash: string | null;
    runtime_id: string | null;
  };
  runtime_drift: {
    drift_detected: boolean;
    active_server: string;
    inferred_provider: string;
    model_name: string;
    endpoint: string;
    issues: string[];
  };
  packages: Record<string, PackageProbe>;
  available_packages: string[];
  missing_packages: string[];
  model_manager: {
    available: boolean;
    usage_metrics: Record<string, unknown> | null;
    error: string | null;
  };
  probe?: {
    enabled: boolean;
    status: string;
    healthy: boolean;
    runtime_supported: boolean;
    endpoint_configured: boolean;
    profile: string;
    limits: {
      timeout_seconds: number;
      max_attempts: number;
      max_top_k: number;
      max_layer_count: number;
      max_prompt_tokens: number;
    };
  };
  reuse: {
    brain: {
      path: string;
      available: boolean;
      purpose: string;
    };
    diagnostics: Array<{ id: string; purpose: string }>;
  };
  summary: {
    active_model: string;
    provider: string;
    runtime_label: string;
    introspection_ready: boolean;
  };
  graph?: {
    nodes: Array<{
      id: string;
      label: string;
      kind: string;
      status: string;
    }>;
    edges: Array<{
      from: string;
      to: string;
      label: string;
    }>;
    summary: {
      nodes: number;
      edges: number;
      available_packages: number;
      missing_packages: number;
      drift_issues: number;
    };
  };
};

export type SnapshotResponse = {
  success: boolean;
  snapshot: IntrospectionSnapshot;
};

export type SnapshotComparison = {
  before: {
    label: string;
    drift: boolean;
    available_packages: number;
    missing_packages: number;
    issues: number;
  };
  after: {
    label: string;
    drift: boolean;
    available_packages: number;
    missing_packages: number;
    issues: number;
  };
  delta: {
    available_packages: number;
    missing_packages: number;
    issues: number;
  };
};

export type AnalysisTimelinePath = "answer_path" | "internals_path";

export type AnalysisTimelineEntry = {
  id: string;
  label: string;
  status: string;
  detail: string;
  reason_code?: string | null;
  path?: AnalysisTimelinePath;
  at_ms: number;
  progress?: number;
};

export type AnalysisProcessStep = {
  component: string | null;
  action: string | null;
  status: string | null;
  details: string | null;
  elapsed_ms?: number | null;
  chunks?: number | null;
  total_ms?: number | null;
  chars?: number | null;
  truncated?: boolean | null;
  prompt_context_truncated?: boolean | null;
  hidden_prompts_count?: number | null;
  prompt_trimmed?: boolean | null;
};

export type AnalysisProcessTrace = {
  request_id: string;
  status: string;
  step_count: number;
  trace_step_count?: number | null;
  steps: AnalysisProcessStep[];
  first_chunk_ms?: number | null;
  response_chunks?: number | null;
  response_chars?: number | null;
  total_ms?: number | null;
  chars_per_second?: number | null;
  response_truncated?: boolean | null;
  prompt_trimmed?: boolean | null;
  context_preview_truncated?: boolean | null;
  adapter_applied?: boolean | null;
  adapter_id?: string | null;
};

export type RagFocusEntity = {
  id: string;
  label: string;
  kind: string;
  active: boolean;
};

export type RagFocusEvidenceEdge = {
  id: string;
  from: string;
  to: string;
  label: string;
  active: boolean;
};

export type RagFocusGrounding = "strong" | "medium" | "weak" | "unknown";

export type RagFocusStepStatus = "done" | "running" | "pending";

export type RagFocusStep = {
  id: "retrieval_started" | "entities_linked" | "context_packed" | "answer_grounded";
  status: RagFocusStepStatus;
};

export type RagFocusModel = {
  source: string;
  query: string;
  entities: RagFocusEntity[];
  evidenceEdges: RagFocusEvidenceEdge[];
  answerEvidenceLinks: Array<{
    id: string;
    fragment: string;
    edgeIds: string[];
    entityIds: string[];
  }>;
  activeEntityIds: string[];
  grounding: RagFocusGrounding;
  steps: RagFocusStep[];
};

export type OperatorConclusionVerdict = "grounded" | "weakly_grounded" | "ungrounded";

export type OperatorConclusionModel = {
  verdict: OperatorConclusionVerdict;
  confidenceTier: "high" | "medium" | "low";
  tone: BadgeTone;
  reasons: string[];
  reasonCodes: string[];
  partial: boolean;
  coveragePercent: number | null;
  streamQuality: string | null;
  internalsQuality: string | null;
};

export type LogitLensTopToken = {
  token: string;
  raw_token?: string | null;
  token_index: number;
  score: number;
};

export type LogitLensCheckpoint = {
  id: string;
  percent: number;
  layer: number;
  top_k: LogitLensTopToken[];
  top_token: string | null;
  confidence: number | null;
  changed: boolean;
};

export type LogitLensSignals = {
  early_unstable: boolean;
  late_stabilized: boolean;
  low_confidence_path: boolean;
};

export type LogitLensModel = {
  source: string;
  status: string;
  code: string | null;
  message: string | null;
  runtime_label: string | null;
  input_tokens: string[];
  output_tokens: string[];
  raw_input_tokens: string[];
  raw_output_tokens: string[];
  checkpoints: LogitLensCheckpoint[];
  signals: LogitLensSignals;
  interpretability: {
    interpretable: boolean;
    confidence_band: string;
    token_noise_ratio: number;
    readable_top_tokens: number;
    total_top_tokens: number;
  };
  diagnostics: Record<string, unknown>;
};

export type AttentionModel = {
  source: string;
  status: string;
  code: string | null;
  message: string | null;
  runtime_label: string | null;
  tokens: string[];
  layers: Array<{
    layer: number;
    heads: Array<{
      head: number;
      top_links: Array<{
        from_index: number;
        to_index: number;
        from_token: string;
        to_token: string;
        weight: number;
      }>;
    }>;
  }>;
  diagnostics: Record<string, unknown>;
};

export type SaliencyModel = {
  source: string;
  status: string;
  code: string | null;
  message: string | null;
  runtime_label: string | null;
  method: string | null;
  target_output_token_index: number | null;
  target_output_token: string | null;
  token_weights: Array<{
    token: string;
    token_index: number;
    weight: number;
  }>;
  diagnostics: Record<string, unknown>;
};

export type AnalysisPhase = "idle" | "requesting" | "streaming" | "first_chunk" | "completed";

type AnalysisCapabilityPayload = {
  available?: boolean;
  source?: string;
  status?: string;
  reason?: string;
  availability_class?: "native_ok" | "proxy_ok" | "unavailable" | "failed" | string;
};

export type AnalysisResult = {
  status: string;
  analysis: {
    prompt: string;
    response: string;
    chunk_count: number;
    events: string[];
    timeline: AnalysisTimelineEntry[];
    timeline_step_count?: number;
    elapsed_ms: number;
    provider: string;
    model: string;
    runtime_label: string;
    request_ready_ms?: number;
    response_received_ms?: number;
    snapshot_after_ms?: number;
    error?: string;
    error_code?: string;
    process?: AnalysisProcessTrace | null;
    rag_focus?: {
      source?: string;
      query?: string;
      entities?: Array<{ id?: string; label?: string; kind?: string; active?: boolean }>;
      evidence_edges?: Array<{
        id?: string;
        from?: string;
        to?: string;
        label?: string;
        active?: boolean;
      }>;
      active_entity_ids?: string[];
      grounding_score?: number;
      answer_evidence_links?: Array<{
        id?: string;
        fragment?: string;
        edge_ids?: string[];
        entity_ids?: string[];
      }>;
    } | null;
    rag_profile?: {
      source?: string;
      entities_count?: number;
      evidence_edges_count?: number;
      active_entities_count?: number;
      grounding_score?: number | null;
    } | null;
    logit_lens?: {
      source?: string;
      status?: string;
      code?: string | null;
      message?: string | null;
      runtime_label?: string | null;
      input_tokens?: string[];
      output_tokens?: string[];
      raw_input_tokens?: string[];
      raw_output_tokens?: string[];
      checkpoints?: Array<{
        id?: string;
        percent?: number;
        layer?: number;
        top_k?: Array<{
          token?: string;
          raw_token?: string;
          token_index?: number;
          score?: number;
        }>;
        top_token?: string | null;
        confidence?: number | null;
        changed?: boolean;
      }>;
      signals?: {
        early_unstable?: boolean;
        late_stabilized?: boolean;
        low_confidence_path?: boolean;
      };
      interpretability?: {
        interpretable?: boolean;
        confidence_band?: string;
        token_noise_ratio?: number;
        readable_top_tokens?: number;
        total_top_tokens?: number;
      };
      diagnostics?: Record<string, unknown>;
    } | null;
    attention?: {
      source?: string;
      status?: string;
      code?: string | null;
      message?: string | null;
      runtime_label?: string | null;
      tokens?: string[];
      layers?: Array<{
        layer?: number;
        heads?: Array<{
          head?: number;
          top_links?: Array<{
            from_index?: number;
            to_index?: number;
            from_token?: string;
            to_token?: string;
            weight?: number;
          }>;
        }>;
      }>;
      diagnostics?: Record<string, unknown>;
    } | null;
    saliency?: {
      source?: string;
      status?: string;
      code?: string | null;
      message?: string | null;
      runtime_label?: string | null;
      method?: string | null;
      target_output_token_index?: number | null;
      target_output_token?: string | null;
      token_weights?: Array<{
        token?: string;
        token_index?: number;
        weight?: number;
      }>;
      diagnostics?: Record<string, unknown>;
    } | null;
    logit_profile?: {
      source?: string;
      status?: string;
      checkpoints_count?: number;
      interpretable?: boolean;
      confidence_band?: string;
      token_noise_ratio?: number;
    } | null;
    input_profile?: {
      prompt_chars?: number;
      prompt_tokens_est?: number;
      context_tokens_est?: number;
      system_tokens_est?: number;
      context_preview_available?: boolean;
      prompt_trimmed?: boolean;
      context_preview_truncated?: boolean;
      hidden_prompts_count?: number;
    } | null;
    generation_profile?: {
      max_tokens?: number | null;
      temperature?: number | null;
      top_p?: number | null;
      top_p_requested?: number | null;
      top_p_applied?: number | null;
      top_p_source?: string;
      top_p_status?: string;
      adapter_applied?: boolean | null;
      adapter_id?: string | null;
      fallback_signal?: string;
    } | null;
    stream_profile?: {
      time_to_stream_open_ms?: number | null;
      time_to_first_byte_ms?: number | null;
      time_to_first_byte_estimated?: boolean;
      time_to_first_byte_source?: string;
      time_to_first_content_ms?: number | null;
      time_to_response_done_ms?: number | null;
      chunk_count?: number;
      event_count?: number;
      chunk_intervals_ms?: number[];
      chunk_interval_p50_ms?: number | null;
      chunk_interval_p95_ms?: number | null;
      chars_per_second?: number | null;
      stream_quality?: string;
    } | null;
    evidence_coverage?: {
      fragments_total?: number;
      fragments_linked?: number;
      coverage_percent?: number;
      orphan_fragments?: number;
    } | null;
    operator_conclusion?: {
      verdict?: string;
      confidence_tier?: string;
      partial?: boolean;
      reason_codes?: string[];
      stream_quality?: string;
      internals_quality?: string;
      evidence_coverage_percent?: number;
      token_noise_ratio?: number;
    } | null;
    analysis_capabilities?: {
      attention?: AnalysisCapabilityPayload;
      saliency?: AnalysisCapabilityPayload;
      logit_lens?: AnalysisCapabilityPayload;
      available_count?: number;
      total_count?: number;
      probe_profile?: string;
      probe_enabled?: boolean;
      probe_healthy?: boolean;
      runtime_supported?: boolean;
      endpoint_configured?: boolean;
      model_whitelisted?: boolean;
      limits?: {
        timeout_seconds?: number;
        max_attempts?: number;
        max_top_k?: number;
        max_layer_count?: number;
        max_head_count?: number;
        max_prompt_tokens?: number;
      };
      internals_verdict?: string;
    } | null;
    run_trends?: {
      runs?: number;
      window?: number;
      runtime_trace_rate?: number;
      probe_runtime_rate?: number;
      high_coverage_rate?: number;
      live_streaming_rate?: number;
      avg_first_content_ms?: number | null;
      avg_noise_ratio?: number | null;
    } | null;
  } | null;
  snapshot_after?: IntrospectionSnapshot;
  skipped_reason?: string;
};

export type BadgeTone = "success" | "warning" | "neutral" | "danger";

export type AnalysisUpdateFn = (
  analysis: NonNullable<AnalysisResult["analysis"]>,
) => NonNullable<AnalysisResult["analysis"]>;

export type GraphNodeDetails = {
  title: string;
  lines: string[];
};
