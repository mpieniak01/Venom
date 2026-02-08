"use client";

import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MarkdownPreview } from "@/components/ui/markdown";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { statusTone } from "@/lib/status";
import type { HistoryRequestDetail, Task } from "@/lib/types";

type FeedbackState = {
  rating?: "up" | "down" | null;
  comment?: string;
  message?: string | null;
};

type ContextPreviewMeta = {
  preview?: string | null;
  truncated?: boolean | null;
  hiddenPrompts?: number | null;
  mode?: string | null;
};

type RuntimeContext = {
  status: string | null;
  error: string | Record<string, unknown> | null;
};

type RuntimeErrorMeta = {
  errorClass: string | null;
  details: string[];
  promptPreview: string | null;
  promptContext: string | null;
  promptContextTruncated: boolean;
};

const RUNTIME_ERROR_CLASSES = [
  "routing_mismatch",
  "execution_contract_violation",
  "provider_unreachable",
  "timeout",
  "rate_limited",
  "runtime_error",
  "agent_error",
  "validation_error",
  "cancelled",
] as const;

function extractRuntimeContext(selectedTask: Task | null): RuntimeContext | null {
  const runtime = selectedTask?.context_history?.["llm_runtime"];
  if (!runtime || typeof runtime !== "object") return null;

  const ctx = runtime as Record<string, unknown>;
  const statusValue = ctx["status"];
  const errorValue = ctx["error"];

  return {
    status: typeof statusValue === "string" ? statusValue : null,
    error:
      typeof errorValue === "string" || (typeof errorValue === "object" && errorValue)
        ? (errorValue as string | Record<string, unknown>)
        : null,
  };
}

function parseRuntimeErrorDetails(errorDetails: Record<string, unknown>): string[] {
  const details: string[] = [];
  const missing = errorDetails["missing"];
  if (Array.isArray(missing) && missing.length > 0) {
    details.push(`missing: ${missing[0]}`);
  }

  const expectedHash = errorDetails["expected_hash"];
  const actualHash = errorDetails["actual_hash"];
  if (typeof expectedHash === "string") details.push(`expected_hash: ${expectedHash.slice(0, 8)}`);
  if (typeof actualHash === "string") details.push(`active_hash: ${actualHash.slice(0, 8)}`);

  const expectedRuntime = errorDetails["expected_runtime"];
  const actualRuntime = errorDetails["actual_runtime"];
  if (typeof expectedRuntime === "string") details.push(`expected_runtime: ${expectedRuntime}`);
  if (typeof actualRuntime === "string") details.push(`active_runtime: ${actualRuntime}`);

  return details;
}

function parseRuntimeTokenInfo(errorDetails: Record<string, unknown>): string | null {
  const tokenInfo: { max?: number; input?: number; requested?: number } = {};
  if (typeof errorDetails.max_context_tokens === "number") tokenInfo.max = errorDetails.max_context_tokens;
  if (typeof errorDetails.input_tokens === "number") tokenInfo.input = errorDetails.input_tokens;
  if (typeof errorDetails.requested_max_tokens === "number") tokenInfo.requested = errorDetails.requested_max_tokens;

  if (!tokenInfo.max && !tokenInfo.input && !tokenInfo.requested) return null;
  const parts: string[] = [];
  if (tokenInfo.max) parts.push(`max_ctx=${tokenInfo.max}`);
  if (tokenInfo.input) parts.push(`input=${tokenInfo.input}`);
  if (tokenInfo.requested) parts.push(`requested=${tokenInfo.requested}`);
  return `tokens: ${parts.join(" / ")}`;
}

function parseRuntimeErrorMeta(error: RuntimeContext["error"]): RuntimeErrorMeta | null {
  if (!error) return null;

  if (typeof error === "string") {
    const errorClass = RUNTIME_ERROR_CLASSES.find((entry) => error.includes(entry)) ?? null;
    return {
      errorClass,
      details: [],
      promptPreview: null,
      promptContext: null,
      promptContextTruncated: false,
    };
  }

  const errorObj = error as Record<string, unknown>;
  const errorDetails =
    typeof errorObj.error_details === "object" && errorObj.error_details
      ? (errorObj.error_details as Record<string, unknown>)
      : {};
  const details = parseRuntimeErrorDetails(errorDetails);
  const tokenInfo = parseRuntimeTokenInfo(errorDetails);
  if (tokenInfo) details.push(tokenInfo);

  const stage = errorObj.stage;
  if (typeof stage === "string") details.push(`stage: ${stage}`);

  return {
    errorClass:
      (typeof errorObj.error_class === "string" && errorObj.error_class) ||
      (typeof errorObj.error_code === "string" && errorObj.error_code) ||
      null,
    details,
    promptPreview: typeof errorDetails.prompt_preview === "string" ? errorDetails.prompt_preview : null,
    promptContext: typeof errorDetails.prompt_context === "string" ? errorDetails.prompt_context : null,
    promptContextTruncated:
      typeof errorDetails.prompt_context_truncated === "boolean"
        ? errorDetails.prompt_context_truncated
        : false,
  };
}

function parseSimpleResponse(historyDetail: HistoryRequestDetail | null) {
  if (!historyDetail) return null;
  if (historyDetail.result) return { text: historyDetail.result, truncated: false };
  if (!historyDetail.steps || historyDetail.steps.length === 0) return null;

  const responseStep = [...historyDetail.steps]
    .reverse()
    .find((step) => step.component === "SimpleMode" && step.action === "response");
  if (!responseStep?.details) return null;

  const raw = responseStep.details.trim();
  if (raw.startsWith("{")) {
    try {
      const parsed = JSON.parse(raw) as { response?: string; truncated?: boolean };
      if (typeof parsed.response === "string") {
        return { text: parsed.response, truncated: !!parsed.truncated };
      }
    } catch {
      return null;
    }
  }

  const responseMatch = raw.match(/response=([\s\S]*)$/);
  if (responseMatch?.[1]) return { text: responseMatch[1].trim(), truncated: false };

  const previewMatch = raw.match(/preview=([\s\S]*)$/);
  if (previewMatch?.[1]) return { text: previewMatch[1].trim(), truncated: true };

  return null;
}

type CockpitRequestDetailDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onClose: () => void;
  historyDetail: HistoryRequestDetail | null;
  loadingHistory: boolean;
  historyError: string | null;
  selectedRequestId: string | null;
  selectedTask: Task | null;
  uiTimingEntry?: { historyMs?: number; ttftMs?: number } | null;
  llmStartAt?: string | null;
  payloadSessionMeta?: Record<string, unknown>;
  payloadForcedRoute?: Record<string, unknown>;
  payloadGenerationParams?: Record<string, unknown>;
  payloadContextUsed?: Record<string, unknown>;
  contextPreviewMeta?: ContextPreviewMeta | null;
  copyStepsMessage: string | null;
  onCopyDetailSteps: () => void;
  feedbackByRequest: Record<string, FeedbackState>;
  feedbackSubmittingId: string | null;
  onFeedbackSubmit: (requestId: string, payload?: { rating?: "up" | "down"; comment?: string }) => void;
  onUpdateFeedbackState: (
    requestId: string,
    patch: Partial<FeedbackState>,
  ) => void;
  t: (key: string, replacements?: Record<string, string | number>) => string;
};

export function CockpitRequestDetailDrawer({
  open,
  onOpenChange,
  onClose,
  historyDetail,
  loadingHistory,
  historyError,
  selectedRequestId,
  selectedTask,
  uiTimingEntry,
  llmStartAt,
  payloadSessionMeta,
  payloadForcedRoute,
  payloadGenerationParams,
  payloadContextUsed,
  contextPreviewMeta,
  copyStepsMessage,
  onCopyDetailSteps,
  feedbackByRequest,
  feedbackSubmittingId,
  onFeedbackSubmit,
  onUpdateFeedbackState,
  t,
}: CockpitRequestDetailDrawerProps) {
  const selectedTaskRuntime = useMemo(() => extractRuntimeContext(selectedTask), [selectedTask]);
  const runtimeErrorMeta = useMemo(
    () => parseRuntimeErrorMeta(selectedTaskRuntime?.error ?? null),
    [selectedTaskRuntime?.error],
  );
  const simpleResponse = useMemo(() => parseSimpleResponse(historyDetail), [historyDetail]);
  const requestModeLabel = useMemo(() => {
    if (contextPreviewMeta?.mode === "direct") return "direct";
    if (contextPreviewMeta?.mode === "normal") return "normal";
    const hasSimple = historyDetail?.steps?.some(
      (step) => step.component === "SimpleMode",
    );
    if (hasSimple) return "direct";
    return "normal";
  }, [contextPreviewMeta?.mode, historyDetail?.steps]);

  return (
    <Sheet
      open={open}
      onOpenChange={(nextOpen) => {
        onOpenChange(nextOpen);
        if (!nextOpen) {
          onClose();
        }
      }}
    >
      <SheetContent className="max-h-[90vh] overflow-y-auto pr-2">
        <SheetHeader>
          <SheetTitle>
            {t("cockpit.requestDetails.drawerTitle")}{" "}
            {historyDetail?.request_id ?? selectedRequestId ?? ""}
          </SheetTitle>
          <SheetDescription>
            {t("cockpit.requestDetails.drawerDescription")}
          </SheetDescription>
        </SheetHeader>
        {!historyDetail && !loadingHistory && !historyError && (
          <p className="text-sm text-zinc-500">
            {t("cockpit.requestDetails.emptyHint")}
          </p>
        )}
        {loadingHistory && (
          <p className="text-sm text-zinc-400">{t("cockpit.requestDetails.loading")}</p>
        )}
        {historyError && (
          <p className="text-sm text-rose-300">{historyError}</p>
        )}
        {historyDetail && (
          <>
            <div className="mt-4 rounded-2xl box-base p-4">
              <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                {t("cockpit.requestDetails.promptTitle")}
              </p>
              <div className="mt-2 text-sm text-white">
                <MarkdownPreview
                  content={historyDetail.prompt}
                  emptyState={t("cockpit.requestDetails.promptEmpty")}
                />
              </div>
            </div>
            {(contextPreviewMeta ||
              payloadGenerationParams ||
              payloadSessionMeta ||
              payloadForcedRoute ||
              payloadContextUsed) && (
                <div className="mt-4 rounded-2xl box-muted p-4">
                  <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                    {t("cockpit.requestDetails.payloadTitle")}
                  </p>
                  <div className="mt-3 grid gap-3 text-xs text-zinc-300">
                    {payloadSessionMeta && (
                      <div>
                        <p className="text-zinc-500">
                          {t("cockpit.requestDetails.sessionContext")}
                        </p>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-zinc-100">
                          {JSON.stringify(payloadSessionMeta, null, 2)}
                        </pre>
                      </div>
                    )}
                    {payloadForcedRoute && (
                      <div>
                        <p className="text-zinc-500">
                          {t("cockpit.requestDetails.forcedRouting")}
                        </p>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-zinc-100">
                          {JSON.stringify(payloadForcedRoute, null, 2)}
                        </pre>
                      </div>
                    )}
                    {payloadGenerationParams && (
                      <div>
                        <p className="text-zinc-500">
                          {t("cockpit.requestDetails.generationParams")}
                        </p>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-zinc-100">
                          {JSON.stringify(payloadGenerationParams, null, 2)}
                        </pre>
                      </div>
                    )}
                    {payloadContextUsed && (
                      <div>
                        <p className="text-zinc-500">
                          {t("cockpit.requestDetails.contextUsed")}
                        </p>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-zinc-100">
                          {JSON.stringify(payloadContextUsed, null, 2)}
                        </pre>
                      </div>
                    )}
                    {contextPreviewMeta && (
                      <div>
                        <div className="flex flex-wrap items-center gap-2 text-zinc-400">
                          <span>{t("cockpit.requestDetails.contextPreview")}</span>
                          {contextPreviewMeta.hiddenPrompts !== null && (
                            <Badge tone="neutral">
                              {t("cockpit.requestDetails.hiddenLabel")}:{" "}
                              {contextPreviewMeta.hiddenPrompts}
                            </Badge>
                          )}
                          {contextPreviewMeta.mode && (
                            <Badge tone="neutral">
                              {t("cockpit.requestDetails.modeLabel")}:{" "}
                              {contextPreviewMeta.mode}
                            </Badge>
                          )}
                        </div>
                        {contextPreviewMeta.preview ? (
                          <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-zinc-100">
                            {contextPreviewMeta.preview}
                          </pre>
                        ) : (
                          <p className="mt-2 text-zinc-500">
                            {t("cockpit.requestDetails.contextPreviewEmpty")}
                          </p>
                        )}
                        {contextPreviewMeta.truncated && (
                          <p className="mt-2 text-[11px] text-zinc-500">
                            {t("cockpit.requestDetails.contextPreviewTruncated")}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            {(requestModeLabel || simpleResponse || runtimeErrorMeta) && (
              <div className="mt-4 rounded-2xl box-muted p-4">
                <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                  {t("cockpit.requestDetails.diagnosticsTitle")}
                </p>
                <div className="mt-3 space-y-3 text-xs text-zinc-300">
                  {requestModeLabel && (
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-zinc-500">
                        {t("cockpit.requestDetails.modeLabel")}:
                      </span>
                      <Badge tone="neutral">{requestModeLabel}</Badge>
                    </div>
                  )}
                  {simpleResponse && (
                    <div>
                      <p className="text-zinc-500">
                        {t("cockpit.requestDetails.simpleResponse")}
                      </p>
                      <div className="mt-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2">
                        <MarkdownPreview
                          content={simpleResponse.text}
                          emptyState={t("cockpit.requestDetails.responseEmpty")}
                        />
                      </div>
                      {simpleResponse.truncated && (
                        <p className="mt-2 text-[11px] text-zinc-500">
                          {t("cockpit.requestDetails.responseTruncated")}
                        </p>
                      )}
                    </div>
                  )}
                  {runtimeErrorMeta && (
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-zinc-500">
                          {t("cockpit.requestDetails.runtimeError")}
                        </span>
                        {runtimeErrorMeta.errorClass && (
                          <Badge tone="danger">{runtimeErrorMeta.errorClass}</Badge>
                        )}
                      </div>
                      {runtimeErrorMeta.details.length > 0 && (
                        <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] text-zinc-400">
                          {runtimeErrorMeta.details.map((detail) => (
                            <li key={detail}>{detail}</li>
                          ))}
                        </ul>
                      )}
                      {runtimeErrorMeta.promptPreview && (
                        <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words text-[11px] text-zinc-300">
                          {runtimeErrorMeta.promptPreview}
                        </pre>
                      )}
                      {runtimeErrorMeta.promptContextTruncated && (
                        <p className="mt-2 text-[11px] text-zinc-500">
                          {t("cockpit.requestDetails.contextTruncated")}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
            {(historyDetail.model || historyDetail.llm_provider || historyDetail.llm_endpoint) && (
              <div className="mt-4 rounded-2xl box-muted p-4">
                <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                  {t("cockpit.requestDetails.modelInfoTitle")}
                </p>
                <div className="mt-3 grid gap-2 text-xs text-zinc-300 sm:grid-cols-2">
                  {(historyDetail.model || historyDetail.llm_model) && (
                    <div className="overflow-hidden">
                      <span className="block truncate text-zinc-500">
                        {t("cockpit.requestDetails.modelLabel")}
                      </span>
                      <div className="text-sm text-zinc-100 truncate" title={historyDetail.model || historyDetail.llm_model || ""}>
                        {historyDetail.model || historyDetail.llm_model}
                      </div>
                    </div>
                  )}
                  {historyDetail.llm_provider && (
                    <div className="overflow-hidden">
                      <span className="block truncate text-zinc-500">
                        {t("cockpit.requestDetails.providerLabel")}
                      </span>
                      <div className="text-sm text-zinc-100 truncate" title={historyDetail.llm_provider}>
                        {historyDetail.llm_provider}
                      </div>
                    </div>
                  )}
                  {historyDetail.llm_endpoint && (
                    <div className="overflow-hidden">
                      <span className="block truncate text-zinc-500">
                        {t("cockpit.requestDetails.endpointLabel")}
                      </span>
                      <div className="text-sm text-zinc-100 truncate" title={historyDetail.llm_endpoint}>
                        {historyDetail.llm_endpoint}
                      </div>
                    </div>
                  )}
                  {historyDetail.llm_runtime_id && (
                    <div className="overflow-hidden">
                      <span className="block truncate text-zinc-500">
                        {t("cockpit.requestDetails.runtimeIdLabel")}
                      </span>
                      <div className="text-sm text-zinc-100 truncate font-mono" title={historyDetail.llm_runtime_id}>
                        {historyDetail.llm_runtime_id.slice(0, 8)}...
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
            {uiTimingEntry && (
              <div className="mt-4 rounded-2xl box-muted p-4">
                <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                  {t("cockpit.requestDetails.uiTimingsTitle")}
                </p>
                <div className="mt-2 grid gap-2 text-xs text-zinc-300 sm:grid-cols-2">
                  <div>
                    <span className="text-zinc-400">
                      {t("cockpit.requestDetails.uiTimingHistory")}
                    </span>
                    <div className="text-sm text-white">
                      {uiTimingEntry.historyMs !== undefined
                        ? `${Math.round(uiTimingEntry.historyMs)} ms`
                        : "—"}
                    </div>
                  </div>
                  <div>
                    <span className="text-zinc-400">TTFT (UI)</span>
                    <div className="text-sm text-white">
                      {uiTimingEntry.ttftMs !== undefined
                        ? `${Math.round(uiTimingEntry.ttftMs)} ms`
                        : "—"}
                    </div>
                  </div>
                </div>
              </div>
            )}
            {(historyDetail.first_token || historyDetail.streaming || llmStartAt) && (
              <div className="mt-4 rounded-2xl box-muted p-4">
                <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                  {t("cockpit.requestDetails.backendTimingsTitle")}
                </p>
                <div className="mt-2 grid gap-2 text-xs text-zinc-300 sm:grid-cols-2">
                  <div className="overflow-hidden">
                    <span className="block truncate text-zinc-400" title={t("cockpit.requestDetails.backendTimingsAccepted")}>
                      {t("cockpit.requestDetails.backendTimingsAccepted")}
                    </span>
                    <div className="text-sm text-white">
                      {formatDateTime(historyDetail.created_at)}
                    </div>
                  </div>
                  <div className="overflow-hidden">
                    <span className="block truncate text-zinc-400" title={t("cockpit.requestDetails.backendTimingsLlmStart")}>
                      {t("cockpit.requestDetails.backendTimingsLlmStart")}
                    </span>
                    <div className="text-sm text-white">
                      {llmStartAt ? formatDateTime(llmStartAt) : "—"}
                    </div>
                  </div>
                  <div className="overflow-hidden">
                    <span className="block truncate text-zinc-400" title={t("cockpit.requestDetails.backendTimingsFirstToken")}>
                      {t("cockpit.requestDetails.backendTimingsFirstToken")}
                    </span>
                    <div className="text-sm text-white">
                      {historyDetail.first_token?.elapsed_ms != null
                        ? `${Math.round(historyDetail.first_token.elapsed_ms)} ms`
                        : "—"}
                    </div>
                  </div>
                  <div className="overflow-hidden">
                    <span className="block truncate text-zinc-400" title={t("cockpit.requestDetails.backendTimingsFirstChunk")}>
                      {t("cockpit.requestDetails.backendTimingsFirstChunk")}
                    </span>
                    <div className="text-sm text-white">
                      {historyDetail.streaming?.first_chunk_ms != null
                        ? `${Math.round(historyDetail.streaming.first_chunk_ms)} ms`
                        : "—"}
                    </div>
                  </div>
                  <div className="overflow-hidden">
                    <span className="block truncate text-zinc-400" title={t("cockpit.requestDetails.backendTimingsChunks")}>
                      {t("cockpit.requestDetails.backendTimingsChunks")}
                    </span>
                    <div className="text-sm text-white">
                      {historyDetail.streaming?.chunk_count != null
                        ? historyDetail.streaming.chunk_count
                        : "—"}
                    </div>
                  </div>
                  <div className="overflow-hidden">
                    <span className="block truncate text-zinc-400" title={t("cockpit.requestDetails.backendTimingsTotalDuration")}>
                      {t("cockpit.requestDetails.backendTimingsTotalDuration")}
                    </span>
                    <div className="text-sm text-white">
                      {formatDurationSeconds(historyDetail.duration_seconds)}
                    </div>
                  </div>
                </div>
              </div>
            )}
            {selectedRequestId && (
              <div className="mt-4 rounded-2xl box-muted p-4">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400">
                  <span>{t("cockpit.requestDetails.feedbackTitle")}</span>
                </div>
                <div className="mt-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      size="xs"
                      variant={
                        feedbackByRequest[selectedRequestId]?.rating === "up"
                          ? "primary"
                          : "outline"
                      }
                      className={feedbackByRequest[selectedRequestId]?.rating === "up" ? "border-emerald-500/50 bg-emerald-500/20 text-emerald-100" : ""}
                      onClick={() => {
                        onUpdateFeedbackState(selectedRequestId, {
                          rating: "up",
                          comment: "",
                        });
                        onFeedbackSubmit(selectedRequestId, { rating: "up" });
                      }}
                    >
                      {t("cockpit.requestDetails.feedbackUp")}
                    </Button>
                    <Button
                      size="xs"
                      variant={
                        feedbackByRequest[selectedRequestId]?.rating === "down"
                          ? "danger"
                          : "outline"
                      }
                      onClick={() =>
                        onUpdateFeedbackState(selectedRequestId, { rating: "down" })
                      }
                    >
                      {t("cockpit.requestDetails.feedbackDown")}
                    </Button>
                  </div>
                  {feedbackByRequest[selectedRequestId]?.rating === "down" && (
                    <textarea
                      className="mt-3 min-h-[80px] w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-xs text-white outline-none placeholder:text-zinc-500"
                      placeholder={t("cockpit.requestDetails.feedbackPlaceholder")}
                      value={feedbackByRequest[selectedRequestId]?.comment || ""}
                      onChange={(event) =>
                        onUpdateFeedbackState(selectedRequestId, {
                          comment: event.target.value,
                        })
                      }
                    />
                  )}
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {feedbackByRequest[selectedRequestId]?.rating === "down" && (
                      <Button
                        size="xs"
                        variant="outline"
                        disabled={
                          feedbackSubmittingId === selectedRequestId ||
                          !(feedbackByRequest[selectedRequestId]?.comment || "").trim()
                        }
                        onClick={() => onFeedbackSubmit(selectedRequestId)}
                      >
                        {feedbackSubmittingId === selectedRequestId
                          ? t("cockpit.requestDetails.feedbackSubmitting")
                          : t("cockpit.requestDetails.feedbackSubmit")}
                      </Button>
                    )}
                    {feedbackByRequest[selectedRequestId]?.message && (
                      <span className="text-xs text-zinc-400">
                        {feedbackByRequest[selectedRequestId]?.message}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )}
            {selectedTask?.logs && selectedTask.logs.length > 0 && (
              <div className="mt-4 rounded-2xl box-muted p-4">
                <div className="flex items-center justify-between">
                  <h4 className="heading-h4">
                    {t("cockpit.requestDetails.taskLogsTitle", { count: selectedTask.logs.length })}
                  </h4>
                </div>
                <div className="mt-3 max-h-[180px] space-y-2 overflow-y-auto pr-2 text-xs text-zinc-300">
                  {selectedTask.logs.map((log, idx) => (
                    <p
                      key={`task-log-${idx}`}
                      className="rounded-xl border border-white/10 bg-white/5 px-3 py-2"
                    >
                      {log}
                    </p>
                  ))}
                </div>
              </div>
            )}
            <div className="mt-4 space-y-2 rounded-2xl box-muted p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h4 className="heading-h4">
                  {t("cockpit.requestDetails.stepsTitle", { count: historyDetail.steps?.length ?? 0 })}
                </h4>
                <div className="flex flex-wrap gap-2 text-xs">
                  {copyStepsMessage && (
                    <span className="text-emerald-300">{copyStepsMessage}</span>
                  )}
                  <Button
                    variant="outline"
                    size="xs"
                    onClick={onCopyDetailSteps}
                  >
                    {t("cockpit.requestDetails.copyJson")}
                  </Button>
                </div>
              </div>
              <div className="max-h-[45vh] space-y-2 overflow-y-auto pr-2">
                {(historyDetail.steps || []).length === 0 && (
                  <p className="text-hint">{t("cockpit.requestDetails.noSteps")}</p>
                )}
                {(historyDetail.steps || []).map((step, idx) => (
                  <div
                    key={`${historyDetail.request_id}-${idx}`}
                    className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-white">
                        {step.component || t("cockpit.requestDetails.stepFallback")}
                      </span>
                      {step.status && (
                        <Badge tone={statusTone(step.status)}>{step.status}</Badge>
                      )}
                    </div>
                    <p className="text-xs text-zinc-400">
                      {step.action || step.details || t("cockpit.requestDetails.stepNoDescription")}
                    </p>
                    {step.timestamp && (
                      <p className="text-caption">
                        {formatDateTime(step.timestamp)}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-xs">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  onOpenChange(false);
                }}
              >
                {t("cockpit.requestDetails.close")}
              </Button>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatDurationSeconds(value?: number | null) {
  if (!value || value <= 0) return "—";
  if (value < 60) return `${value.toFixed(1)}s`;
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60);
  return `${minutes}m ${seconds}s`;
}
