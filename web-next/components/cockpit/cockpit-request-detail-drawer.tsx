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
  t: (key: string) => string;
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
  const selectedTaskRuntime = useMemo(() => {
    const runtime = selectedTask?.context_history?.["llm_runtime"];
    if (runtime && typeof runtime === "object") {
      const ctx = runtime as Record<string, unknown>;
      const statusValue = ctx["status"];
      const errorValue = ctx["error"];
      return {
        status: typeof statusValue === "string" ? statusValue : null,
        error:
          typeof errorValue === "string" || (typeof errorValue === "object" && errorValue)
            ? errorValue
            : null,
      };
    }
    return null;
  }, [selectedTask]);
  const runtimeErrorMeta = useMemo(() => {
    const error = selectedTaskRuntime?.error;
    if (!error) return null;
    if (typeof error === "string") {
      const classes = [
        "routing_mismatch",
        "execution_contract_violation",
        "provider_unreachable",
        "timeout",
        "rate_limited",
        "runtime_error",
        "agent_error",
        "validation_error",
        "cancelled",
      ];
      const errorClass = classes.find((entry) => error.includes(entry)) ?? null;
      return { errorClass, details: [], promptPreview: null, promptContext: null, promptContextTruncated: false };
    }
    const errorObj = error as Record<string, unknown>;
    const errorClass =
      (typeof errorObj.error_class === "string" && errorObj.error_class) ||
      (typeof errorObj.error_code === "string" && errorObj.error_code) ||
      null;
    const details: string[] = [];
    const errorDetails =
      typeof errorObj.error_details === "object" && errorObj.error_details
        ? (errorObj.error_details as Record<string, unknown>)
        : {};
    const tokenInfo: { max?: number; input?: number; requested?: number } = {};
    if (typeof errorDetails.max_context_tokens === "number") {
      tokenInfo.max = errorDetails.max_context_tokens;
    }
    if (typeof errorDetails.input_tokens === "number") {
      tokenInfo.input = errorDetails.input_tokens;
    }
    if (typeof errorDetails.requested_max_tokens === "number") {
      tokenInfo.requested = errorDetails.requested_max_tokens;
    }
    const promptPreview =
      typeof errorDetails.prompt_preview === "string"
        ? errorDetails.prompt_preview
        : null;
    const promptContext =
      typeof errorDetails.prompt_context === "string"
        ? errorDetails.prompt_context
        : null;
    const promptContextTruncated =
      typeof errorDetails.prompt_context_truncated === "boolean"
        ? errorDetails.prompt_context_truncated
        : false;
    const missing = errorDetails["missing"];
    if (Array.isArray(missing) && missing.length > 0) {
      details.push(`missing: ${missing[0]}`);
    }
    const expectedHash = errorDetails["expected_hash"];
    const actualHash = errorDetails["actual_hash"];
    if (typeof expectedHash === "string") {
      details.push(`expected_hash: ${expectedHash.slice(0, 8)}`);
    }
    if (typeof actualHash === "string") {
      details.push(`active_hash: ${actualHash.slice(0, 8)}`);
    }
    const expectedRuntime = errorDetails["expected_runtime"];
    const actualRuntime = errorDetails["actual_runtime"];
    if (typeof expectedRuntime === "string") {
      details.push(`expected_runtime: ${expectedRuntime}`);
    }
    if (typeof actualRuntime === "string") {
      details.push(`active_runtime: ${actualRuntime}`);
    }
    const stage = errorObj.stage;
    if (typeof stage === "string") {
      details.push(`stage: ${stage}`);
    }
    if (tokenInfo.max || tokenInfo.input || tokenInfo.requested) {
      const parts = [];
      if (tokenInfo.max) parts.push(`max_ctx=${tokenInfo.max}`);
      if (tokenInfo.input) parts.push(`input=${tokenInfo.input}`);
      if (tokenInfo.requested) parts.push(`requested=${tokenInfo.requested}`);
      details.push(`tokens: ${parts.join(" / ")}`);
    }
    return {
      errorClass,
      details,
      promptPreview,
      promptContext,
      promptContextTruncated,
    };
  }, [selectedTaskRuntime?.error]);
  const simpleResponse = useMemo(() => {
    if (historyDetail?.result) {
      return { text: historyDetail.result, truncated: false };
    }
    if (!historyDetail?.steps || historyDetail.steps.length === 0) return null;
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
    if (responseMatch?.[1]) {
      return { text: responseMatch[1].trim(), truncated: false };
    }
    const previewMatch = raw.match(/preview=([\s\S]*)$/);
    if (previewMatch?.[1]) {
      return { text: previewMatch[1].trim(), truncated: true };
    }
    return null;
  }, [historyDetail?.steps]);
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
            Szczegóły requestu {historyDetail?.request_id ?? selectedRequestId ?? ""}
          </SheetTitle>
          <SheetDescription>
            {"Dane z `/api/v1/history/requests` – kliknięcie w czat lub listę historii otwiera ten panel."}
          </SheetDescription>
        </SheetHeader>
        {!historyDetail && !loadingHistory && !historyError && (
          <p className="text-sm text-zinc-500">
            Wybierz request z Cockpitu, aby zobaczyć szczegóły.
          </p>
        )}
        {loadingHistory && (
          <p className="text-sm text-zinc-400">Ładuję szczegóły requestu...</p>
        )}
        {historyError && (
          <p className="text-sm text-rose-300">{historyError}</p>
        )}
        {historyDetail && (
          <>
            <div className="mt-4 rounded-2xl box-base p-4">
              <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                Prompt
              </p>
              <div className="mt-2 text-sm text-white">
                <MarkdownPreview
                  content={historyDetail.prompt}
                  emptyState="Brak promptu dla tego requestu."
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
                    Payload do modelu
                  </p>
                  <div className="mt-3 grid gap-3 text-xs text-zinc-300">
                    {payloadSessionMeta && (
                      <div>
                        <p className="text-zinc-500">Kontekst sesji</p>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-zinc-100">
                          {JSON.stringify(payloadSessionMeta, null, 2)}
                        </pre>
                      </div>
                    )}
                    {payloadForcedRoute && (
                      <div>
                        <p className="text-zinc-500">Routing wymuszony</p>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-zinc-100">
                          {JSON.stringify(payloadForcedRoute, null, 2)}
                        </pre>
                      </div>
                    )}
                    {payloadGenerationParams && (
                      <div>
                        <p className="text-zinc-500">Parametry generacji</p>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-zinc-100">
                          {JSON.stringify(payloadGenerationParams, null, 2)}
                        </pre>
                      </div>
                    )}
                    {payloadContextUsed && (
                      <div>
                        <p className="text-zinc-500">Uzyty kontekst</p>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-zinc-100">
                          {JSON.stringify(payloadContextUsed, null, 2)}
                        </pre>
                      </div>
                    )}
                    {contextPreviewMeta && (
                      <div>
                        <div className="flex flex-wrap items-center gap-2 text-zinc-400">
                          <span>Podglad kontekstu</span>
                          {contextPreviewMeta.hiddenPrompts !== null && (
                            <Badge tone="neutral">
                              hidden: {contextPreviewMeta.hiddenPrompts}
                            </Badge>
                          )}
                          {contextPreviewMeta.mode && (
                            <Badge tone="neutral">
                              tryb: {contextPreviewMeta.mode}
                            </Badge>
                          )}
                        </div>
                        {contextPreviewMeta.preview ? (
                          <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-zinc-100">
                            {contextPreviewMeta.preview}
                          </pre>
                        ) : (
                          <p className="mt-2 text-zinc-500">Brak podgladu kontekstu.</p>
                        )}
                        {contextPreviewMeta.truncated && (
                          <p className="mt-2 text-[11px] text-zinc-500">
                            Podglad skrócony (limit logowania).
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
                  Diagnostyka requestu
                </p>
                <div className="mt-3 space-y-3 text-xs text-zinc-300">
                  {requestModeLabel && (
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-zinc-500">Tryb:</span>
                      <Badge tone="neutral">{requestModeLabel}</Badge>
                    </div>
                  )}
                  {simpleResponse && (
                    <div>
                      <p className="text-zinc-500">Odpowiedz (SimpleMode)</p>
                      <div className="mt-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2">
                        <MarkdownPreview
                          content={simpleResponse.text}
                          emptyState="Brak odpowiedzi."
                        />
                      </div>
                      {simpleResponse.truncated && (
                        <p className="mt-2 text-[11px] text-zinc-500">
                          Odpowiedz skrocona (limit logowania).
                        </p>
                      )}
                    </div>
                  )}
                  {runtimeErrorMeta && (
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-zinc-500">Błąd runtime</span>
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
                          Podglad kontekstu skrocony.
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
                  Model Info
                </p>
                <div className="mt-3 grid gap-2 text-xs text-zinc-300 sm:grid-cols-2">
                  {(historyDetail.model || historyDetail.llm_model) && (
                    <div className="overflow-hidden">
                      <span className="block truncate text-zinc-500">Model</span>
                      <div className="text-sm text-zinc-100 truncate" title={historyDetail.model || historyDetail.llm_model || ""}>
                        {historyDetail.model || historyDetail.llm_model}
                      </div>
                    </div>
                  )}
                  {historyDetail.llm_provider && (
                    <div className="overflow-hidden">
                      <span className="block truncate text-zinc-500">Serwer / Provider</span>
                      <div className="text-sm text-zinc-100 truncate" title={historyDetail.llm_provider}>
                        {historyDetail.llm_provider}
                      </div>
                    </div>
                  )}
                  {historyDetail.llm_endpoint && (
                    <div className="overflow-hidden">
                      <span className="block truncate text-zinc-500">Endpoint</span>
                      <div className="text-sm text-zinc-100 truncate" title={historyDetail.llm_endpoint}>
                        {historyDetail.llm_endpoint}
                      </div>
                    </div>
                  )}
                  {historyDetail.llm_runtime_id && (
                    <div className="overflow-hidden">
                      <span className="block truncate text-zinc-500">Runtime ID</span>
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
                  UI timings
                </p>
                <div className="mt-2 grid gap-2 text-xs text-zinc-300 sm:grid-cols-2">
                  <div>
                    <span className="text-zinc-400">submit → historia</span>
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
                    <span className="block truncate text-zinc-400" title={t("cockpit.requestDetails.backendTimingsTotal")}>
                      {t("cockpit.requestDetails.backendTimingsTotal")}
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
                  <span>Feedback</span>
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
                      Kciuk w górę
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
                      Kciuk w dół
                    </Button>
                  </div>
                  {feedbackByRequest[selectedRequestId]?.rating === "down" && (
                    <textarea
                      className="mt-3 min-h-[80px] w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-xs text-white outline-none placeholder:text-zinc-500"
                      placeholder="Opisz krótko, co było nie tak i czego oczekujesz."
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
                          ? "Wysyłam..."
                          : "Wyślij feedback"}
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
                    Logi zadania ({selectedTask.logs.length})
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
                  Kroki RequestTracer ({historyDetail.steps?.length ?? 0})
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
                    Kopiuj JSON
                  </Button>
                </div>
              </div>
              <div className="max-h-[45vh] space-y-2 overflow-y-auto pr-2">
                {(historyDetail.steps || []).length === 0 && (
                  <p className="text-hint">Brak kroków do wyświetlenia.</p>
                )}
                {(historyDetail.steps || []).map((step, idx) => (
                  <div
                    key={`${historyDetail.request_id}-${idx}`}
                    className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-white">
                        {step.component || "step"}
                      </span>
                      {step.status && (
                        <Badge tone={statusTone(step.status)}>{step.status}</Badge>
                      )}
                    </div>
                    <p className="text-xs text-zinc-400">
                      {step.action || step.details || "Brak opisu kroku."}
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
                Zamknij
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
