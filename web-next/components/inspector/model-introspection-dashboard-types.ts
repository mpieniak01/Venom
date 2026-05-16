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

export type AnalysisTimelineEntry = {
  id: string;
  label: string;
  status: string;
  detail: string;
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

export type AnalysisPhase = "idle" | "requesting" | "streaming" | "first_chunk" | "completed";

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
    process?: AnalysisProcessTrace | null;
  } | null;
  snapshot_after?: IntrospectionSnapshot;
  skipped_reason?: string;
};

export type BadgeTone = "success" | "warning" | "neutral";

export type AnalysisUpdateFn = (
  analysis: NonNullable<AnalysisResult["analysis"]>,
) => NonNullable<AnalysisResult["analysis"]>;

export type GraphNodeDetails = {
  title: string;
  lines: string[];
};
