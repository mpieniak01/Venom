"use client";

import type {
  AnalysisProcessTrace,
  AnalysisPhase,
  AnalysisTimelineEntry,
  AttentionModel,
  BadgeTone,
  GraphNodeDetails,
  IntrospectionSnapshot,
  LogitLensModel,
  OperatorConclusionModel,
  ModelArchitectureGraphReadiness,
  RagFocusGrounding,
  RagFocusModel,
  RagFocusStepStatus,
  SaliencyModel,
} from "@/components/inspector/model-introspection-dashboard-types";

export type OperatorFinalStatus = "idle" | "running" | "completed" | "failed" | "skipped";
export type OperatorStreamMode =
  | "pending"
  | "live_streaming"
  | "single_chunk"
  | "single_chunk_delayed"
  | "buffered_delivery"
  | "no_content";

export function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

export function clampPercent(value: number): number {
  if (Number.isFinite(value) && !Number.isNaN(value)) {
    return Math.max(0, Math.min(100, value));
  }
  return 0;
}

export function shortenTraceId(requestId: string | null | undefined): string {
  if (!requestId) {
    return "—";
  }
  if (requestId.length > 8) {
    return `${requestId.slice(0, 8)}…`;
  }
  return requestId;
}

export function timelineBadgeTone(status: string): BadgeTone {
  if (status === "done") {
    return "success";
  }
  if (status === "failed") {
    return "danger";
  }
  if (status === "running") {
    return "warning";
  }
  return "neutral";
}

export function splitAnswerHighlights(answer: string): string[] {
  if (!answer.trim()) {
    return [];
  }
  return answer
    .replace(/\s+/g, " ")
    .split(/(?<=[.!?])\s+/)
    .map((segment) => segment.trim())
    .filter(Boolean)
    .slice(0, 4);
}

export function getPhaseTone(phase: AnalysisPhase): BadgeTone {
  if (phase === "completed") {
    return "success";
  }
  if (phase === "streaming" || phase === "first_chunk") {
    return "warning";
  }
  return "neutral";
}

export function getPhaseLabel(phase: AnalysisPhase): string {
  if (phase === "first_chunk") {
    return "first chunk";
  }
  return phase;
}

export function getAnalysisPhase(args: {
  analysisVisible: boolean;
  analysisLoading: boolean;
  analysisStatus: string | undefined;
  firstChunkMs: number | null;
  chunkCount: number;
}): AnalysisPhase {
  const {
    analysisVisible,
    analysisLoading,
    analysisStatus,
    firstChunkMs,
    chunkCount,
  } = args;
  if (analysisVisible) {
    if (analysisStatus === "completed") {
      return "completed";
    }
    if (analysisStatus === "running") {
      if (chunkCount > 0) {
        return "streaming";
      }
      return "requesting";
    }
    if (firstChunkMs != null || chunkCount > 0) {
      return "first_chunk";
    }
    return "idle";
  }
  if (analysisLoading) {
    return "requesting";
  }
  return "idle";
}

export function getAnswerTone(
  answer: string,
  analysisVisible: boolean,
): BadgeTone {
  if (analysisVisible && answer) {
    return /potrzebuj|need more context|more context/i.test(answer)
      ? "warning"
      : "success";
  }
  return "neutral";
}

export function getPackageRingColor(packageCoveragePercent: number): string {
  if (packageCoveragePercent >= 100) {
    return "#047857";
  }
  if (packageCoveragePercent >= 80) {
    return "#059669";
  }
  return "#f59e0b";
}

export function getOrbCoreShadow(phase: AnalysisPhase): string {
  if (phase === "completed") {
    return "0 0 16px rgba(4,120,87,0.26)";
  }
  if (phase === "streaming" || phase === "first_chunk") {
    return "0 0 18px rgba(6,182,212,0.28)";
  }
  if (phase === "requesting") {
    return "0 0 18px rgba(245,158,11,0.28)";
  }
  return "0 0 14px rgba(113,113,122,0.22)";
}

export function getAnalysisProgressBarColor(phase: AnalysisPhase): string {
  if (phase === "completed") {
    return "#10b981";
  }
  if (phase === "streaming" || phase === "first_chunk") {
    return "#06b6d4";
  }
  if (phase === "requesting") {
    return "#f59e0b";
  }
  return "#71717a";
}

export function getGraphNodeTone(status: string): BadgeTone {
  if (status === "available" || status === "connected" || status === "ready") {
    return "success";
  }
  if (status === "missing" || status === "offline") {
    return "warning";
  }
  return "neutral";
}

export function computeAnalysisProgress(args: {
  analysisVisible: boolean;
  analysisTimelineProgress: number;
  analysisStepCount: number;
  chunkCount: number;
  firstChunkMs: number | null | undefined;
  elapsedMs: number;
  analysisStatus: string | undefined;
}): number {
  const {
    analysisVisible,
    analysisTimelineProgress,
    analysisStepCount,
    chunkCount,
    firstChunkMs,
    elapsedMs,
    analysisStatus,
  } = args;
  if (!analysisVisible) {
    return 0;
  }
  const capProgress = (value: number): number => {
    const cappedValue = analysisStatus === "completed" ? value : Math.min(value, 90);
    return clampPercent(cappedValue);
  };
  if (analysisTimelineProgress > 0) {
    return capProgress(analysisTimelineProgress);
  }
  const estimatedProgress = Math.min(
    100,
    analysisStepCount * 18 + (firstChunkMs == null ? 0 : 20),
  );
  const noChunkYet = chunkCount === 0 && firstChunkMs == null;
  if (analysisStatus === "running" && noChunkYet) {
    const waitingProgress = 30 + Math.min(50, elapsedMs / 250);
    return capProgress(Math.max(estimatedProgress, waitingProgress));
  }
  if (noChunkYet) {
    return capProgress(Math.min(estimatedProgress, 30));
  }
  return capProgress(estimatedProgress);
}

export function getOrbSubtitle(args: {
  analysisStatus: string | undefined;
  analysisActive: boolean;
  chunkCount: number;
  analysisStepCount: number;
  idleLabel: string;
  chunksLabel?: string;
  stepsLabel?: string;
  completedLabel?: string;
}): string {
  const {
    analysisStatus,
    analysisActive,
    chunkCount,
    analysisStepCount,
    idleLabel,
    chunksLabel,
    stepsLabel,
    completedLabel,
  } = args;
  const chunkUnit = chunksLabel ?? "chunk(s)";
  const stepUnit = stepsLabel ?? "step(s)";
  const doneLabel = completedLabel ?? "completed";
  if (analysisStatus === "completed") {
    return `${chunkCount} ${chunkUnit} · ${analysisStepCount} ${stepUnit} · ${doneLabel}`;
  }
  if (analysisActive) {
    return `${chunkCount} ${chunkUnit} · ${analysisStepCount} ${stepUnit}`;
  }
  return idleLabel;
}

export function getAnswerStatusLabel(args: {
  response: string;
  analysisRunning: boolean;
  answeredLabel: string;
  streamingLabel: string;
  awaitingLabel: string;
}): string {
  if (args.response) {
    return args.answeredLabel;
  }
  if (args.analysisRunning) {
    return args.streamingLabel;
  }
  return args.awaitingLabel;
}

export function resolveOperatorFinalStatus(args: {
  analysisStatus: string | undefined;
  analysisVisible: boolean;
}): OperatorFinalStatus {
  const { analysisStatus, analysisVisible } = args;
  if (!analysisVisible) {
    return "idle";
  }
  if (analysisStatus === "running") {
    return "running";
  }
  if (analysisStatus === "completed") {
    return "completed";
  }
  if (analysisStatus === "failed") {
    return "failed";
  }
  if (analysisStatus === "skipped") {
    return "skipped";
  }
  return "idle";
}

export function getOperatorFinalStatusTone(
  status: OperatorFinalStatus,
): BadgeTone {
  if (status === "completed") {
    return "success";
  }
  if (status === "failed") {
    return "warning";
  }
  if (status === "running") {
    return "warning";
  }
  return "neutral";
}

export function resolveOperatorStreamMode(args: {
  analysisVisible: boolean;
  chunkCount: number;
  firstChunkMs: number | null;
}): OperatorStreamMode {
  const { analysisVisible, chunkCount, firstChunkMs } = args;
  if (!analysisVisible) {
    return "pending";
  }
  if (chunkCount <= 0) {
    return "no_content";
  }
  if (chunkCount > 1) {
    return "live_streaming";
  }
  const delayedThresholdMs = 1000;
  if ((firstChunkMs ?? 0) >= delayedThresholdMs) {
    return "single_chunk_delayed";
  }
  return "single_chunk";
}

export function getOperatorStreamModeTone(
  mode: OperatorStreamMode,
): BadgeTone {
  if (mode === "live_streaming") {
    return "success";
  }
  if (mode === "single_chunk_delayed") {
    return "warning";
  }
  if (mode === "no_content") {
    return "warning";
  }
  return "neutral";
}

export function resolveFallbackSignal(args: {
  adapterApplied: boolean | null | undefined;
  adapterId: string | null | undefined;
}): "used" | "none" | "unknown" {
  const { adapterApplied, adapterId } = args;
  if (adapterApplied == null && !adapterId) {
    return "unknown";
  }
  if (adapterApplied || Boolean(adapterId)) {
    return "used";
  }
  return "none";
}

export function getFallbackSignalTone(
  fallbackSignal: "used" | "none" | "unknown",
): BadgeTone {
  if (fallbackSignal === "used") {
    return "warning";
  }
  if (fallbackSignal === "none") {
    return "success";
  }
  return "neutral";
}

function resolveRagFocusStepStatus(args: {
  done: boolean;
  analysisStatus: string | undefined;
  fallbackRunning: boolean;
}): RagFocusStepStatus {
  const { done, analysisStatus, fallbackRunning } = args;
  if (done) {
    return "done";
  }
  if (analysisStatus === "running" && fallbackRunning) {
    return "running";
  }
  return "pending";
}

function resolveGroundingFromScore(score: number | null): RagFocusGrounding {
  if (score == null) {
    return "unknown";
  }
  if (score >= 0.85) {
    return "strong";
  }
  if (score >= 0.55) {
    return "medium";
  }
  return "weak";
}

function buildFallbackRagEntities(
  snapshot: IntrospectionSnapshot | null,
): Array<{ id: string; label: string; kind: string }> {
  const graphNodes = snapshot?.graph?.nodes ?? [];
  const filteredNodes = graphNodes.filter((node) => node.id !== "runtime");
  return filteredNodes.slice(0, 6).map((node) => ({
    id: node.id,
    label: node.label,
    kind: node.kind,
  }));
}

function buildFallbackRagEvidence(args: {
  entities: Array<{ id: string; label: string; kind: string }>;
  snapshot: IntrospectionSnapshot | null;
}): Array<{ id: string; from: string; to: string; label: string }> {
  const { entities, snapshot } = args;
  const entityIds = new Set(entities.map((entity) => entity.id));
  const graphEdges = snapshot?.graph?.edges ?? [];
  const selectedEdges = graphEdges
    .filter((edge) => entityIds.has(edge.from) || entityIds.has(edge.to))
    .slice(0, 8)
    .map((edge, index) => ({
      id: `edge:${index + 1}`,
      from: edge.from,
      to: edge.to,
      label: edge.label,
    }));

  if (selectedEdges.length > 0) {
    return selectedEdges;
  }

  return entities.slice(0, 4).map((entity, index) => ({
    id: `edge:${index + 1}`,
    from: "query",
    to: entity.id,
    label: entity.kind === "reuse" ? "retrieval source" : "context signal",
  }));
}

function resolveRagFocusGrounding(args: {
  entitiesCount: number;
  evidenceCount: number;
  analysisStatus: string | undefined;
  analysisProcess: AnalysisProcessTrace | null;
}): RagFocusGrounding {
  const { entitiesCount, evidenceCount, analysisStatus, analysisProcess } = args;
  if (analysisStatus !== "completed") {
    return "unknown";
  }
  if (entitiesCount === 0) {
    return "weak";
  }
  const ratio = evidenceCount / Math.max(1, entitiesCount);
  const contextBoost = analysisProcess?.context_preview_truncated === false ? 0.15 : 0;
  const truncationPenalty = analysisProcess?.response_truncated ? -0.2 : 0;
  return resolveGroundingFromScore(Math.max(0, Math.min(1, ratio + contextBoost + truncationPenalty)));
}

function resolveRagFocusActiveEntities(args: {
  entityIds: string[];
  evidenceEdges: Array<{ from: string; to: string; label: string }>;
  analysisStatus: string | undefined;
  hasFirstChunk: boolean;
}): string[] {
  const { entityIds, evidenceEdges, analysisStatus, hasFirstChunk } = args;
  if (analysisStatus === "completed") {
    const activeSet = new Set<string>();
    for (const edge of evidenceEdges) {
      if (entityIds.includes(edge.from)) {
        activeSet.add(edge.from);
      }
      if (entityIds.includes(edge.to)) {
        activeSet.add(edge.to);
      }
    }
    if (activeSet.size > 0) {
      return Array.from(activeSet);
    }
    return entityIds.slice(0, 3);
  }
  if (analysisStatus === "running") {
    const runningCount = hasFirstChunk ? 3 : 2;
    return entityIds.slice(0, runningCount);
  }
  return [];
}

export function getRagGroundingTone(grounding: RagFocusGrounding): BadgeTone {
  if (grounding === "strong") {
    return "success";
  }
  if (grounding === "medium" || grounding === "weak") {
    return "warning";
  }
  return "neutral";
}

function normalizeLensToken(token: unknown): string {
  const raw =
    typeof token === "string" || typeof token === "number"
      ? String(token)
      : "";
  const noMarker = raw.startsWith("▁") ? raw.slice(1) : raw;
  const trimmed = noMarker.trim();
  return trimmed || "?";
}

function normalizeLogitLensCheckpoint(
  checkpoint: {
    id?: string;
    percent?: number;
    layer?: number;
    top_k?: Array<{ token?: string; raw_token?: string; token_index?: number; score?: number }>;
    top_token?: string | null;
    confidence?: number | null;
    changed?: boolean;
  },
): NonNullable<LogitLensModel["checkpoints"]>[number] | null {
  const rawTopK = Array.isArray(checkpoint.top_k) ? checkpoint.top_k : [];
  const topK = rawTopK
    .filter((item) => typeof item?.score === "number")
    .map((item) => ({
      token: normalizeLensToken(item.token),
      raw_token: resolveRawToken(item.raw_token, item.token),
      token_index: typeof item.token_index === "number" ? item.token_index : -1,
      score: Number(item.score),
    }))
    .sort((left, right) => right.score - left.score);
  if (topK.length === 0) {
    return null;
  }
  const percent = typeof checkpoint.percent === "number" ? checkpoint.percent : 0;
  const layer = typeof checkpoint.layer === "number" ? checkpoint.layer : -1;
  return {
    id: String(checkpoint.id || `cp_${percent}`),
    percent,
    layer,
    top_k: topK,
    top_token: normalizeLensToken(checkpoint.top_token ?? topK[0]?.token),
    confidence:
      typeof checkpoint.confidence === "number" ? checkpoint.confidence : null,
    changed: Boolean(checkpoint.changed),
  };
}

function resolveRawToken(rawToken: unknown, token: unknown): string | null {
  if (typeof rawToken === "string") {
    return rawToken;
  }
  if (typeof token === "string") {
    return token;
  }
  return null;
}

function resolveRawTokens(
  rawTokens: unknown,
  normalizedTokens: string[] | undefined,
): string[] {
  if (Array.isArray(rawTokens)) {
    return rawTokens.map((token) => String(token ?? ""));
  }
  if (Array.isArray(normalizedTokens)) {
    return normalizedTokens.map((token) => String(token ?? ""));
  }
  return [];
}

type LogitLensPayloadInput = {
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
};

type AttentionPayloadInput = {
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
};

type SaliencyPayloadInput = {
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
};

export function buildLogitLensModel(
  payload: LogitLensPayloadInput | null | undefined,
): LogitLensModel | null {
  if (!payload) {
    return null;
  }
  const checkpointsRaw = Array.isArray(payload.checkpoints)
    ? payload.checkpoints
    : [];
  const checkpoints = checkpointsRaw
    .map((checkpoint) => normalizeLogitLensCheckpoint(checkpoint))
    .filter(
      (
        checkpoint,
      ): checkpoint is NonNullable<LogitLensModel["checkpoints"]>[number] =>
        checkpoint !== null,
    );
  return {
    source: String(payload.source || "probe_unavailable"),
    status: String(payload.status || "probe_unavailable"),
    code: payload.code ?? null,
    message: payload.message ?? null,
    runtime_label: payload.runtime_label ?? null,
    input_tokens: Array.isArray(payload.input_tokens)
      ? payload.input_tokens.map((token) => normalizeLensToken(token))
      : [],
    output_tokens: Array.isArray(payload.output_tokens)
      ? payload.output_tokens.map((token) => normalizeLensToken(token))
      : [],
    raw_input_tokens: resolveRawTokens(payload.raw_input_tokens, payload.input_tokens),
    raw_output_tokens: resolveRawTokens(payload.raw_output_tokens, payload.output_tokens),
    checkpoints,
    signals: {
      early_unstable: Boolean(payload.signals?.early_unstable),
      late_stabilized: Boolean(payload.signals?.late_stabilized),
      low_confidence_path: Boolean(payload.signals?.low_confidence_path),
    },
    interpretability: {
      interpretable: Boolean(payload.interpretability?.interpretable),
      confidence_band: String(payload.interpretability?.confidence_band || "unknown"),
      token_noise_ratio:
        typeof payload.interpretability?.token_noise_ratio === "number"
          ? payload.interpretability.token_noise_ratio
          : 1,
      readable_top_tokens:
        typeof payload.interpretability?.readable_top_tokens === "number"
          ? payload.interpretability.readable_top_tokens
          : 0,
      total_top_tokens:
        typeof payload.interpretability?.total_top_tokens === "number"
          ? payload.interpretability.total_top_tokens
          : 0,
    },
    diagnostics:
      payload.diagnostics && typeof payload.diagnostics === "object"
        ? payload.diagnostics
        : {},
  };
}

export function getLogitLensSignalTone(
  active: boolean,
): BadgeTone {
  if (active) {
    return "warning";
  }
  return "success";
}

export function getDataSourceTone(source: string): BadgeTone {
  if (source === "runtime_trace" || source === "probe_runtime") {
    return "success";
  }
  if (source === "graph_fallback" || source === "probe_unavailable") {
    return "warning";
  }
  return "neutral";
}

export function buildAttentionModel(
  payload: AttentionPayloadInput | null | undefined,
): AttentionModel | null {
  if (!payload) {
    return null;
  }
  const layersRaw = Array.isArray(payload.layers) ? payload.layers : [];
  const layers = layersRaw
    .map((layer) => {
      if (typeof layer?.layer !== "number") {
        return null;
      }
      const headsRaw = Array.isArray(layer.heads) ? layer.heads : [];
      const heads = headsRaw
        .map((head) => {
          if (typeof head?.head !== "number") {
            return null;
          }
          const linksRaw = Array.isArray(head.top_links) ? head.top_links : [];
          const topLinks = linksRaw
            .filter(
              (link) =>
                typeof link?.from_index === "number" &&
                typeof link?.to_index === "number" &&
                typeof link?.weight === "number",
            )
            .map((link) => ({
              from_index: Number(link.from_index),
              to_index: Number(link.to_index),
              from_token: normalizeLensToken(link.from_token),
              to_token: normalizeLensToken(link.to_token),
              weight: Number(link.weight),
            }))
            .sort((left, right) => right.weight - left.weight)
            .slice(0, 6);
          if (topLinks.length === 0) {
            return null;
          }
          return {
            head: Number(head.head),
            top_links: topLinks,
          };
        })
        .filter(
          (
            head,
          ): head is NonNullable<AttentionModel["layers"]>[number]["heads"][number] =>
            head !== null,
        );
      if (heads.length === 0) {
        return null;
      }
      heads.sort((left, right) => left.head - right.head);
      return {
        layer: Number(layer.layer),
        heads,
      };
    })
    .filter(
      (
        layer,
      ): layer is NonNullable<AttentionModel["layers"]>[number] => layer !== null,
    );

  return {
    source: String(payload.source || "probe_unavailable"),
    status: String(payload.status || "probe_unavailable"),
    code: payload.code ?? null,
    message: payload.message ?? null,
    runtime_label: payload.runtime_label ?? null,
    tokens: Array.isArray(payload.tokens)
      ? payload.tokens.map((token) => normalizeLensToken(token)).slice(0, 64)
      : [],
    layers,
    diagnostics:
      payload.diagnostics && typeof payload.diagnostics === "object"
        ? payload.diagnostics
        : {},
  };
}

export function buildSaliencyModel(
  payload: SaliencyPayloadInput | null | undefined,
): SaliencyModel | null {
  if (!payload) {
    return null;
  }
  const tokenWeightsRaw = Array.isArray(payload.token_weights)
    ? payload.token_weights
    : [];
  const token_weights = tokenWeightsRaw
    .filter(
      (item) =>
        typeof item?.token_index === "number" && typeof item?.weight === "number",
    )
    .map((item) => ({
      token: normalizeLensToken(item.token),
      token_index: Number(item.token_index),
      weight: Number(item.weight),
    }))
    .sort((left, right) => Math.abs(right.weight) - Math.abs(left.weight))
    .slice(0, 24);

  return {
    source: String(payload.source || "probe_unavailable"),
    status: String(payload.status || "probe_unavailable"),
    code: payload.code ?? null,
    message: payload.message ?? null,
    runtime_label: payload.runtime_label ?? null,
    method:
      typeof payload.method === "string" && payload.method
        ? payload.method
        : null,
    target_output_token_index:
      typeof payload.target_output_token_index === "number"
        ? payload.target_output_token_index
        : null,
    target_output_token:
      typeof payload.target_output_token === "string"
        ? normalizeLensToken(payload.target_output_token)
        : null,
    token_weights,
    diagnostics:
      payload.diagnostics && typeof payload.diagnostics === "object"
        ? payload.diagnostics
        : {},
  };
}

export function buildRagFocusModel(args: {
  analysisPrompt: string;
  analysisStatus: string | undefined;
  chunkCount: number;
  analysisTimeline: AnalysisTimelineEntry[];
  analysisProcess: AnalysisProcessTrace | null;
  snapshot: IntrospectionSnapshot | null;
  ragFocusPayload:
    | {
        source?: string;
        query?: string;
        grounding_score?: number | null;
        entities?: Array<{ id?: string; label?: string; kind?: string; active?: boolean }>;
        evidence_edges?: Array<{ id?: string; from?: string; to?: string; label?: string; active?: boolean }>;
        active_entity_ids?: string[];
        answer_evidence_links?: Array<{
          id?: string;
          fragment?: string;
          edge_ids?: string[];
          entity_ids?: string[];
        }>;
      }
    | null
    | undefined;
}): RagFocusModel | null {
  const {
    analysisPrompt,
    analysisStatus,
    chunkCount,
    analysisTimeline,
    analysisProcess,
    snapshot,
    ragFocusPayload,
  } = args;
  const query = (ragFocusPayload?.query || analysisPrompt || "").trim();
  if (!query) {
    return null;
  }
  const source = String(ragFocusPayload?.source || "graph_fallback");

  const payloadEntities =
    ragFocusPayload?.entities
      ?.filter((entity) => Boolean(entity.id) && Boolean(entity.label))
      .map((entity) => ({
        id: String(entity.id),
        label: String(entity.label),
        kind: String(entity.kind || "entity"),
      })) ?? [];
  const entities = payloadEntities.length > 0 ? payloadEntities : buildFallbackRagEntities(snapshot);
  const payloadEvidence =
    ragFocusPayload?.evidence_edges
      ?.filter((edge) => Boolean(edge.from) && Boolean(edge.to))
      .map((edge, index) => ({
        id: String(edge.id || `edge:${index + 1}`),
        from: String(edge.from),
        to: String(edge.to),
        label: String(edge.label || "evidence"),
      })) ?? [];
  const evidenceEdges =
    payloadEvidence.length > 0
      ? payloadEvidence
      : buildFallbackRagEvidence({ entities, snapshot });

  const entityIds = entities.map((entity) => entity.id);
  const timelineIds = new Set(analysisTimeline.map((step) => step.id));
  const hasFirstChunk = timelineIds.has("first_chunk") || chunkCount > 0;
  const activeEntityIds =
    ragFocusPayload?.active_entity_ids?.filter((id) => entityIds.includes(id)) ??
    resolveRagFocusActiveEntities({
      entityIds,
      evidenceEdges,
      analysisStatus,
      hasFirstChunk,
    });

  const answerEvidenceLinks =
    ragFocusPayload?.answer_evidence_links
      ?.filter((link) => Boolean(link.fragment))
      .map((link, index) => ({
        id: String(link.id || `link:${index + 1}`),
        fragment: String(link.fragment || ""),
        edgeIds: Array.isArray(link.edge_ids)
          ? link.edge_ids
              .map(String)
              .filter((edgeId) => evidenceEdges.some((edge) => edge.id === edgeId))
          : [],
        entityIds: Array.isArray(link.entity_ids)
          ? link.entity_ids
              .map(String)
              .filter((entityId) => entityIds.includes(entityId))
          : [],
      }))
      .filter((link) => link.edgeIds.length > 0)
      .slice(0, 4) ?? [];

  const retrievalStartedDone =
    timelineIds.has("request_ready") || timelineIds.has("stream_opened");
  const entitiesLinkedDone = entities.length > 0;
  const contextPackedDone =
    (analysisProcess?.steps ?? []).some((step) =>
      step.action === "context_preview" || step.action === "prompt_trim",
    ) || timelineIds.has("stream_opened");
  const answerGroundedDone =
    analysisStatus === "completed" && timelineIds.has("response_finalized");

  const steps = [
    {
      id: "retrieval_started" as const,
      status: resolveRagFocusStepStatus({
        done: retrievalStartedDone,
        analysisStatus,
        fallbackRunning: true,
      }),
    },
    {
      id: "entities_linked" as const,
      status: resolveRagFocusStepStatus({
        done: entitiesLinkedDone,
        analysisStatus,
        fallbackRunning: retrievalStartedDone,
      }),
    },
    {
      id: "context_packed" as const,
      status: resolveRagFocusStepStatus({
        done: contextPackedDone,
        analysisStatus,
        fallbackRunning: entitiesLinkedDone,
      }),
    },
    {
      id: "answer_grounded" as const,
      status: resolveRagFocusStepStatus({
        done: answerGroundedDone,
        analysisStatus,
        fallbackRunning: hasFirstChunk,
      }),
    },
  ];
  const groundingFromPayload =
    typeof ragFocusPayload?.grounding_score === "number"
      ? resolveGroundingFromScore(ragFocusPayload.grounding_score)
      : null;

  return {
    source,
    query,
    entities: entities.map((entity) => ({
      ...entity,
      active: activeEntityIds.includes(entity.id),
    })),
    evidenceEdges: evidenceEdges.map((edge) => ({
      ...edge,
      active: activeEntityIds.includes(edge.from) || activeEntityIds.includes(edge.to),
    })),
    answerEvidenceLinks,
    activeEntityIds,
    grounding:
      groundingFromPayload ??
      resolveRagFocusGrounding({
        entitiesCount: entities.length,
        evidenceCount: evidenceEdges.length,
        analysisStatus,
        analysisProcess,
      }),
    steps,
  };
}

export function buildOperatorConclusion(args: {
  analysisVisible: boolean;
  analysisStatus: string | undefined;
  skippedReason?: string | null;
  analysisErrorCode?: string | null;
  analysisTimeline?: AnalysisTimelineEntry[] | null;
  ragFocus: RagFocusModel | null;
  logitLens: LogitLensModel | null;
  operatorConclusionPayload?:
    | {
        verdict?: string;
        confidence_tier?: string;
        partial?: boolean;
        reason_codes?: string[];
        stream_quality?: string;
        internals_quality?: string;
        evidence_coverage_percent?: number;
      }
    | null;
}): OperatorConclusionModel | null {
  const {
    analysisVisible,
    analysisStatus,
    skippedReason,
    analysisErrorCode,
    analysisTimeline,
    ragFocus,
    logitLens,
    operatorConclusionPayload,
  } = args;
  if (!analysisVisible) {
    return null;
  }
  const payloadConclusion = resolveOperatorConclusionFromPayload(operatorConclusionPayload);
  if (analysisStatus === "completed" && payloadConclusion) {
    return payloadConclusion;
  }

  if (analysisStatus === "failed") {
    return {
      verdict: "ungrounded",
      confidenceTier: "low",
      tone: "warning",
      reasons: ["analysis failed"],
      reasonCodes: ["R0_FAILED"],
      partial: true,
      coveragePercent: null,
      streamQuality: null,
      internalsQuality: null,
    };
  }

  if (analysisStatus === "skipped") {
    return buildSkippedOperatorConclusion({
      skippedReason,
      analysisErrorCode,
    });
  }

  if (analysisStatus !== "completed") {
    return buildInProgressOperatorConclusion();
  }

  const ragRuntime = ragFocus?.source === "runtime_trace";
  const logitRuntime = logitLens?.source === "probe_runtime";
  const probeSignal = resolveProbeSignal({
    logitRuntime,
    analysisTimeline,
    logitCode: logitLens?.code ?? null,
    operatorReasonCodes: operatorConclusionPayload?.reason_codes ?? null,
  });
  const hasEvidence = (ragFocus?.evidenceEdges.length ?? 0) > 0;
  const hasAnswerLinks = (ragFocus?.answerEvidenceLinks.length ?? 0) > 0;
  const grounding = ragFocus?.grounding ?? "unknown";

  if (
    ragRuntime &&
    hasEvidence &&
    hasAnswerLinks &&
    (grounding === "strong" || grounding === "medium")
  ) {
    return buildGroundedOperatorConclusion(probeSignal);
  }

  if (hasEvidence || ragRuntime) {
    return buildWeaklyGroundedOperatorConclusion({
      ragRuntime,
      hasAnswerLinks,
      probeSignal,
    });
  }

  return buildUngroundedOperatorConclusion(probeSignal);
}

function buildSkippedOperatorConclusion(args: {
  skippedReason?: string | null;
  analysisErrorCode?: string | null;
}): OperatorConclusionModel {
  const { skippedReason, analysisErrorCode } = args;
  const defaults = {
    verdict: "ungrounded" as const,
    confidenceTier: "low" as const,
    tone: "warning" as const,
    partial: true,
    coveragePercent: null,
    streamQuality: null,
    internalsQuality: null,
  };
  if (
    skippedReason === "model_drift_detected" ||
    analysisErrorCode === "MODEL_DRIFT_DETECTED"
  ) {
    return {
      ...defaults,
      reasons: ["model drift detected"],
      reasonCodes: ["R0_MODEL_DRIFT"],
    };
  }
  const degradedReasonMap: Record<string, { reason: string; code: string }> = {
    DEGRADED_CIRCUIT_OPEN: {
      reason: "degraded mode: circuit breaker open",
      code: "R0_DEGRADED_CIRCUIT",
    },
    DEGRADED_ENDPOINT_UNREACHABLE: {
      reason: "degraded mode: endpoint unreachable",
      code: "R0_DEGRADED_ENDPOINT",
    },
    DEGRADED_POLICY_BLOCK: {
      reason: "degraded mode: policy block",
      code: "R0_DEGRADED_POLICY",
    },
  };
  const degradedReason =
    (analysisErrorCode && degradedReasonMap[analysisErrorCode]) || null;
  if (degradedReason) {
    return {
      ...defaults,
      reasons: [degradedReason.reason],
      reasonCodes: [degradedReason.code],
    };
  }
  return {
    ...defaults,
    reasons: ["analysis skipped"],
    reasonCodes: ["R0_SKIPPED"],
  };
}

export function buildOperatorRunbookSteps(
  reasonCodes: readonly string[] | null | undefined,
): string[] {
  if (!Array.isArray(reasonCodes) || reasonCodes.length === 0) {
    return [];
  }
  const runbookGroups: Array<{ codes: readonly string[]; stepsPrefix: string }> = [
    { codes: ["R0_MODEL_DRIFT"], stepsPrefix: "modelDrift" },
    { codes: ["R0_DEGRADED_ENDPOINT"], stepsPrefix: "degradedEndpoint" },
    { codes: ["R0_DEGRADED_CIRCUIT"], stepsPrefix: "degradedCircuit" },
    { codes: ["R0_DEGRADED_POLICY"], stepsPrefix: "degradedPolicy" },
    { codes: ["R3_PROBE_FALLBACK", "R3_PROBE_PROXY", "R3_PROBE_FAILED"], stepsPrefix: "probeFallback" },
    { codes: ["R4_STREAM_DELAYED"], stepsPrefix: "streamDelayed" },
    { codes: ["R5_LOGIT_NOISE_HIGH"], stepsPrefix: "logitNoiseHigh" },
  ];
  for (const group of runbookGroups) {
    if (group.codes.some((code) => reasonCodes.includes(code))) {
      return [
        `inspector.modelIntrospection.dashboard.results.runbook.${group.stepsPrefix}.step1`,
        `inspector.modelIntrospection.dashboard.results.runbook.${group.stepsPrefix}.step2`,
        `inspector.modelIntrospection.dashboard.results.runbook.${group.stepsPrefix}.step3`,
      ];
    }
  }
  return [];
}

function resolveOperatorConclusionFromPayload(
  payload:
    | {
        verdict?: string;
        confidence_tier?: string;
        partial?: boolean;
        reason_codes?: string[];
        stream_quality?: string;
        internals_quality?: string;
        evidence_coverage_percent?: number;
      }
    | null
    | undefined,
): OperatorConclusionModel | null {
  const verdict = payload?.verdict;
  if (
    verdict !== "grounded" &&
    verdict !== "weakly_grounded" &&
    verdict !== "ungrounded"
  ) {
    return null;
  }
  const confidenceRaw = payload?.confidence_tier;
  const confidenceTier =
    confidenceRaw === "high" || confidenceRaw === "low"
      ? confidenceRaw
      : "medium";
  const reasonCodes = Array.isArray(payload?.reason_codes)
    ? payload.reason_codes.map(String)
    : [];
  const reasons =
    reasonCodes.length > 0
      ? reasonCodes.map((code) => code.toLowerCase().replaceAll("_", " "))
      : ["operator signals ready"];

  return {
    verdict,
    confidenceTier,
    tone: verdict === "grounded" ? "success" : "warning",
    reasons,
    reasonCodes,
    partial: Boolean(payload?.partial),
    coveragePercent:
      typeof payload?.evidence_coverage_percent === "number"
        ? payload.evidence_coverage_percent
        : null,
    streamQuality: payload?.stream_quality ?? null,
    internalsQuality: payload?.internals_quality ?? null,
  };
}

function resolveInternalsQuality(logitRuntime: boolean): "runtime_probe" | "fallback_probe" {
  return logitRuntime ? "runtime_probe" : "fallback_probe";
}

type ProbeSignal = {
  logitRuntime: boolean;
  code: "R3_PROBE_RUNTIME" | "R3_PROBE_PROXY" | "R3_PROBE_FALLBACK" | "R3_PROBE_FAILED";
  label: string;
};

function resolveProbeSignal(args: {
  logitRuntime: boolean;
  analysisTimeline?: AnalysisTimelineEntry[] | null;
  logitCode?: string | null;
  operatorReasonCodes?: string[] | null;
}): ProbeSignal {
  const { logitRuntime, analysisTimeline, logitCode, operatorReasonCodes } = args;
  if (Array.isArray(operatorReasonCodes) && operatorReasonCodes.includes("R3_PROBE_PROXY")) {
    return {
      logitRuntime: true,
      code: "R3_PROBE_PROXY",
      label: "runtime probe active (proxy path)",
    };
  }
  if (typeof logitCode === "string" && logitCode.includes("_proxy_")) {
    return {
      logitRuntime: true,
      code: "R3_PROBE_PROXY",
      label: `runtime probe active (proxy: ${logitCode})`,
    };
  }
  const internalsSteps = (analysisTimeline ?? []).filter((step) =>
    step.id.startsWith("internals:"),
  );
  const failedStep = internalsSteps.find((step) => step.status === "failed");
  if (failedStep) {
    return {
      logitRuntime: false,
      code: "R3_PROBE_FAILED",
      label: failedStep.reason_code ? `probe failed: ${failedStep.reason_code}` : "probe failed",
    };
  }
  const skippedStep = internalsSteps.find((step) => step.status === "skipped");
  if (skippedStep) {
    return {
      logitRuntime: false,
      code: "R3_PROBE_FALLBACK",
      label: skippedStep.reason_code
        ? `probe unavailable: ${skippedStep.reason_code}`
        : "probe unavailable",
    };
  }
  if (logitRuntime) {
    return {
      logitRuntime: true,
      code: "R3_PROBE_RUNTIME",
      label: "runtime probe active",
    };
  }
  return {
    logitRuntime: false,
    code: "R3_PROBE_FALLBACK",
    label: "probe unavailable",
  };
}

function buildInProgressOperatorConclusion(): OperatorConclusionModel {
  return {
    verdict: "weakly_grounded",
    confidenceTier: "low",
    tone: "neutral",
    reasons: ["analysis in progress"],
    reasonCodes: ["R0_IN_PROGRESS"],
    partial: true,
    coveragePercent: null,
    streamQuality: null,
    internalsQuality: null,
  };
}

function buildGroundedOperatorConclusion(probeSignal: ProbeSignal): OperatorConclusionModel {
  const { logitRuntime, code, label } = probeSignal;
  return {
    verdict: "grounded",
    confidenceTier: logitRuntime ? "high" : "medium",
    tone: "success",
    reasons: [
      "runtime trace evidence available",
      "answer fragments linked to evidence",
      label,
    ],
    reasonCodes: ["R1_RUNTIME_TRACE", "R2_COVERAGE_HIGH", code],
    partial: !logitRuntime,
    coveragePercent: null,
    streamQuality: null,
    internalsQuality: resolveInternalsQuality(logitRuntime),
  };
}

function buildWeaklyGroundedOperatorConclusion(args: {
  ragRuntime: boolean;
  hasAnswerLinks: boolean;
  probeSignal: ProbeSignal;
}): OperatorConclusionModel {
  const { ragRuntime, hasAnswerLinks, probeSignal } = args;
  return {
    verdict: "weakly_grounded",
    confidenceTier: "medium",
    tone: "warning",
    reasons: [
      ragRuntime ? "runtime trace partial" : "graph fallback evidence",
      hasAnswerLinks ? "limited answer-to-evidence links" : "missing answer links",
      probeSignal.label,
    ],
    reasonCodes: [
      ragRuntime ? "R1_RUNTIME_TRACE" : "R1_GRAPH_FALLBACK",
      "R2_COVERAGE_MEDIUM",
      probeSignal.code,
    ],
    partial: true,
    coveragePercent: null,
    streamQuality: null,
    internalsQuality: resolveInternalsQuality(probeSignal.logitRuntime),
  };
}

function buildUngroundedOperatorConclusion(probeSignal: ProbeSignal): OperatorConclusionModel {
  return {
    verdict: "ungrounded",
    confidenceTier: "low",
    tone: "warning",
    reasons: [
      "no evidence edges",
      "no answer-to-evidence links",
      probeSignal.label,
    ],
    reasonCodes: ["R1_NO_EVIDENCE", "R2_COVERAGE_LOW", probeSignal.code],
    partial: true,
    coveragePercent: null,
    streamQuality: null,
    internalsQuality: resolveInternalsQuality(probeSignal.logitRuntime),
  };
}

export function getTypeHintText(kind: string): string {
  if (kind === "package") {
    return "Package drilldown uses the same snapshot as runtime health, so it is safe to inspect without triggering extra probes.";
  }
  if (kind === "architecture") {
    return "Architecture graph drilldown should use layer-level nodes and edges instead of runtime/package metadata.";
  }
  if (kind === "probe") {
    return "Probe drilldown shows runtime probe readiness, profile and limits for model internals.";
  }
  if (kind === "reuse") {
    return "Reuse drilldown helps confirm that Brain and diagnostics stay shared rather than duplicated.";
  }
  return "Runtime drilldown summarizes the active runtime, model and analysis attachment points.";
}

function formatElapsedDetails(args: {
  analysisVisible: boolean;
  analysisElapsedMs: number;
}): string {
  const { analysisVisible, analysisElapsedMs } = args;
  if (analysisVisible) {
    return `${analysisElapsedMs.toFixed(1)} ms`;
  }
  return "—";
}

export function buildModelArchitectureGraphReadiness(
  snapshot: IntrospectionSnapshot | null,
): ModelArchitectureGraphReadiness {
  const architectureGraph = snapshot?.architecture_graph ?? null;
  const hasArchitecturePayload = Boolean(
    architectureGraph?.nodes?.length || architectureGraph?.edges?.length,
  );
  const diagnosticGraph = snapshot?.graph ?? null;
  const hasDiagnosticGraph = Boolean(diagnosticGraph?.nodes?.length || diagnosticGraph?.edges?.length);
  const layerCount = architectureGraph?.summary.layer_count ?? 0;
  const blockCount = architectureGraph?.summary.block_count ?? 0;
  const fidelity = architectureGraph?.meta.fidelity ?? "unknown";
  const source = architectureGraph?.meta.source ?? "diagnostic snapshot";
  const generatedAt = architectureGraph?.meta.generated_at ?? null;

  if (hasArchitecturePayload) {
    const hasStructuralFields =
      architectureGraph?.nodes.length > 0 &&
      architectureGraph?.edges.length > 0 &&
      layerCount > 0 &&
      blockCount > 0;
    const status =
      fidelity === "native" && hasStructuralFields
        ? "available"
        : "partial";
    const missingSignals: string[] = [];
    if (!architectureGraph?.nodes.length) {
      missingSignals.push("architecture nodes missing");
    }
    if (!architectureGraph?.edges.length) {
      missingSignals.push("architecture edges missing");
    }
    if (fidelity !== "native") {
      missingSignals.push(`architecture graph fidelity ${fidelity}`);
    }
    if (!architectureGraph?.meta.generated_at) {
      missingSignals.push("generation timestamp missing");
    }
    return {
      status,
      hasArchitecturePayload,
      hasDiagnosticGraph,
      fidelity,
      source,
      generatedAt,
      nodeCount: architectureGraph?.nodes.length ?? 0,
      edgeCount: architectureGraph?.edges.length ?? 0,
      layerCount,
      blockCount,
      missingSignals,
      recommendedNextStep:
        status === "available"
          ? "Native architecture graph payload is ready for Cytoscape rendering."
          : "Derived architecture graph is available, but native layer/block metadata still needs to be supplied before treating it as final.",
    };
  }

  const missingSignals = [
    "architecture_graph payload missing",
    "current graph is diagnostic-only",
    "layer and block metadata still need to be produced",
  ];
  if (!hasDiagnosticGraph) {
    missingSignals.push("snapshot graph missing");
  }
  return {
    status: "missing",
    hasArchitecturePayload: false,
    hasDiagnosticGraph,
    fidelity: "unknown",
    source: "diagnostic snapshot",
    generatedAt: null,
    nodeCount: diagnosticGraph?.nodes?.length ?? 0,
    edgeCount: diagnosticGraph?.edges?.length ?? 0,
    layerCount: 0,
    blockCount: 0,
    missingSignals,
    recommendedNextStep:
      "Add a dedicated architecture_graph payload with layer, block and edge metadata before switching the panel to a model architecture graph.",
  };
}

function getRuntimeGraphNodeDetails(snapshot: IntrospectionSnapshot): GraphNodeDetails {
  return {
    title: "Runtime details",
    lines: [
      `Provider: ${snapshot.runtime.provider}`,
      `Model: ${snapshot.runtime.model}`,
      `Endpoint: ${snapshot.runtime.endpoint ?? "local"}`,
      `Service type: ${snapshot.runtime.service_type}`,
      `Mode: ${snapshot.runtime.mode}`,
    ],
  };
}

function getModelGraphNodeDetails(snapshot: IntrospectionSnapshot): GraphNodeDetails {
  return {
    title: "Model details",
    lines: [
      `Active model: ${snapshot.summary.active_model}`,
      `Runtime label: ${snapshot.summary.runtime_label}`,
      `Drift issues: ${snapshot.runtime_drift.issues.length}`,
    ],
  };
}

function getAnalysisGraphNodeDetails(args: {
  analysisMechanismEnabled: boolean;
  analysisStatus: string | undefined;
  analysisVisible: boolean;
  analysisChunkCount: number;
  analysisElapsedMs: number;
}): GraphNodeDetails {
  const {
    analysisMechanismEnabled,
    analysisStatus,
    analysisVisible,
    analysisChunkCount,
    analysisElapsedMs,
  } = args;
  return {
    title: "Analysis details",
    lines: [
      `Mechanism: ${analysisMechanismEnabled ? "enabled" : "disabled"}`,
      `Status: ${analysisStatus ?? "idle"}`,
      `Content chunks: ${analysisVisible ? analysisChunkCount : 0}`,
      `Elapsed: ${formatElapsedDetails({ analysisVisible, analysisElapsedMs })}`,
    ],
  };
}

function getManagerGraphNodeDetails(snapshot: IntrospectionSnapshot): GraphNodeDetails {
  return {
    title: "ModelManager details",
    lines: [
      `Available: ${snapshot.model_manager.available ? "yes" : "no"}`,
      `Metrics: ${snapshot.model_manager.usage_metrics ? "present" : "absent"}`,
      `Error: ${snapshot.model_manager.error ?? "—"}`,
    ],
  };
}

function getBrainGraphNodeDetails(snapshot: IntrospectionSnapshot): GraphNodeDetails {
  return {
    title: "Reuse details",
    lines: [
      `Path: ${snapshot.reuse.brain.path}`,
      `Available: ${snapshot.reuse.brain.available ? "yes" : "no"}`,
      `Purpose: ${snapshot.reuse.brain.purpose}`,
    ],
  };
}

function getDiagnosticsGraphNodeDetails(snapshot: IntrospectionSnapshot): GraphNodeDetails {
  return {
    title: "Diagnostics reuse",
    lines: snapshot.reuse.diagnostics.map((entry) => `${entry.id}: ${entry.purpose}`),
  };
}

function getProbeGraphNodeDetails(snapshot: IntrospectionSnapshot): GraphNodeDetails {
  const probe = snapshot.probe;
  if (!probe) {
    return {
      title: "Probe details",
      lines: ["Probe metadata unavailable in runtime snapshot."],
    };
  }
  return {
    title: "Probe details",
    lines: [
      `Status: ${probe.status}`,
      `Enabled: ${probe.enabled ? "yes" : "no"}`,
      `Profile: ${probe.profile}`,
      `Top-k limit: ${probe.limits.max_top_k}`,
      `Layer limit: ${probe.limits.max_layer_count}`,
      `Timeout: ${probe.limits.timeout_seconds}s`,
    ],
  };
}

function getPackageGraphNodeDetails(args: {
  snapshot: IntrospectionSnapshot;
  selectedGraphNode: { id: string; label: string; kind: string; status: string };
}): GraphNodeDetails {
  const { snapshot, selectedGraphNode } = args;
  const packageKey = selectedGraphNode.id.replaceAll("package:", "");
  const packageNode = snapshot.packages[packageKey];
  if (packageNode) {
    return {
      title: "Package details",
      lines: [
        `Package: ${packageNode.package}`,
        `Module: ${packageNode.module}`,
        `Available: ${packageNode.available ? "yes" : "no"}`,
        `Version: ${packageNode.version ?? "n/a"}`,
      ],
    };
  }
  return {
    title: "Package details",
    lines: [`Node: ${selectedGraphNode.label}`, `Status: ${selectedGraphNode.status}`],
  };
}

export function resolveSelectedGraphNodeDetails(args: {
  snapshot: IntrospectionSnapshot;
  selectedGraphNode: { id: string; label: string; kind: string; status: string };
  analysisMechanismEnabled: boolean;
  analysisStatus: string | undefined;
  analysisVisible: boolean;
  analysisChunkCount: number;
  analysisElapsedMs: number;
}): GraphNodeDetails {
  const {
    snapshot,
    selectedGraphNode,
    analysisMechanismEnabled,
    analysisStatus,
    analysisVisible,
    analysisChunkCount,
    analysisElapsedMs,
  } = args;

  const nodeId = selectedGraphNode.id;
  if (nodeId === "runtime") return getRuntimeGraphNodeDetails(snapshot);
  if (nodeId === "model") return getModelGraphNodeDetails(snapshot);
  if (nodeId === "analysis") {
    return getAnalysisGraphNodeDetails({
      analysisMechanismEnabled,
      analysisStatus,
      analysisVisible,
      analysisChunkCount,
      analysisElapsedMs,
    });
  }
  if (nodeId === "manager") return getManagerGraphNodeDetails(snapshot);
  if (nodeId === "brain") return getBrainGraphNodeDetails(snapshot);
  if (nodeId === "diagnostics") return getDiagnosticsGraphNodeDetails(snapshot);
  if (nodeId === "probe") return getProbeGraphNodeDetails(snapshot);
  return getPackageGraphNodeDetails({ snapshot, selectedGraphNode });
}
