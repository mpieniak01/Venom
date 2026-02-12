import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MarkdownPreview } from "@/components/ui/markdown";
import { statusTone } from "@/lib/status";
import type { HistoryRequestDetail, HistoryStep } from "@/lib/types";
import {
    formatDateTime,
    formatDurationSeconds,
    RuntimeErrorMeta,
    SimpleResponse,
    ContextPreviewMeta,
    FeedbackState
} from "./drawer-helpers";

export function PromptSection({ prompt, t }: Readonly<{ prompt: string; t: (key: string, options?: Record<string, string | number>) => string }>) {
    return (
        <div className="mt-4 rounded-2xl box-base p-4">
            <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                {t("cockpit.requestDetails.promptTitle")}
            </p>
            <div className="mt-2 text-sm text-white">
                <MarkdownPreview
                    content={prompt}
                    emptyState={t("cockpit.requestDetails.promptEmpty")}
                />
            </div>
        </div>
    );
}

export function PayloadSection({
    payloadSessionMeta,
    payloadForcedRoute,
    payloadGenerationParams,
    payloadContextUsed,
    contextPreviewMeta,
    t
}: Readonly<{
    payloadSessionMeta?: Record<string, unknown>;
    payloadForcedRoute?: Record<string, unknown>;
    payloadGenerationParams?: Record<string, unknown>;
    payloadContextUsed?: Record<string, unknown>;
    contextPreviewMeta?: ContextPreviewMeta | null;
    t: (key: string, options?: Record<string, string | number>) => string;
}>) {
    if (!contextPreviewMeta && !payloadGenerationParams && !payloadSessionMeta && !payloadForcedRoute && !payloadContextUsed) return null;

    return (
        <div className="mt-4 rounded-2xl box-muted p-4">
            <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                {t("cockpit.requestDetails.payloadTitle")}
            </p>
            <div className="mt-3 grid gap-3 text-xs text-zinc-300">
                {payloadSessionMeta && (
                    <div>
                        <p className="text-zinc-500">{t("cockpit.requestDetails.sessionContext")}</p>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-zinc-100">
                            {JSON.stringify(payloadSessionMeta, null, 2)}
                        </pre>
                    </div>
                )}
                {payloadForcedRoute && (
                    <div>
                        <p className="text-zinc-500">{t("cockpit.requestDetails.forcedRouting")}</p>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-zinc-100">
                            {JSON.stringify(payloadForcedRoute, null, 2)}
                        </pre>
                    </div>
                )}
                {payloadGenerationParams && (
                    <div>
                        <p className="text-zinc-500">{t("cockpit.requestDetails.generationParams")}</p>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-zinc-100">
                            {JSON.stringify(payloadGenerationParams, null, 2)}
                        </pre>
                    </div>
                )}
                {payloadContextUsed && (
                    <div>
                        <p className="text-zinc-500">{t("cockpit.requestDetails.contextUsed")}</p>
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
                                    {t("cockpit.requestDetails.hiddenLabel")}: {contextPreviewMeta.hiddenPrompts}
                                </Badge>
                            )}
                            {contextPreviewMeta.mode && (
                                <Badge tone="neutral">
                                    {t("cockpit.requestDetails.modeLabel")}: {contextPreviewMeta.mode}
                                </Badge>
                            )}
                        </div>
                        {contextPreviewMeta.preview ? (
                            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-zinc-100">
                                {contextPreviewMeta.preview}
                            </pre>
                        ) : (
                            <p className="mt-2 text-zinc-500">{t("cockpit.requestDetails.contextPreviewEmpty")}</p>
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
    );
}

export function DiagnosticsSection({
    requestModeLabel,
    simpleResponse,
    runtimeErrorMeta,
    t
}: Readonly<{
    requestModeLabel?: string | null;
    simpleResponse?: SimpleResponse | null;
    runtimeErrorMeta?: RuntimeErrorMeta | null;
    t: (key: string, options?: Record<string, string | number>) => string;
}>) {
    if (!requestModeLabel && !simpleResponse && !runtimeErrorMeta) return null;

    return (
        <div className="mt-4 rounded-2xl box-muted p-4">
            <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                {t("cockpit.requestDetails.diagnosticsTitle")}
            </p>
            <div className="mt-3 space-y-3 text-xs text-zinc-300">
                {requestModeLabel && (
                    <div className="flex flex-wrap items-center gap-2">
                        <span className="text-zinc-500">{t("cockpit.requestDetails.modeLabel")}:</span>
                        <Badge tone="neutral">{requestModeLabel}</Badge>
                    </div>
                )}
                {simpleResponse && (
                    <div>
                        <p className="text-zinc-500">{t("cockpit.requestDetails.simpleResponse")}</p>
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
                            <span className="text-zinc-500">{t("cockpit.requestDetails.runtimeError")}</span>
                            {runtimeErrorMeta.errorClass && <Badge tone="danger">{runtimeErrorMeta.errorClass}</Badge>}
                        </div>
                        {runtimeErrorMeta.details.length > 0 && (
                            <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] text-zinc-400">
                                {runtimeErrorMeta.details.map((detail) => <li key={detail}>{detail}</li>)}
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
    );
}

export function ModelInfoSection({ historyDetail, t }: Readonly<{ historyDetail: HistoryRequestDetail; t: (key: string, options?: Record<string, string | number>) => string }>) {
    if (!historyDetail.model && !historyDetail.llm_provider && !historyDetail.llm_endpoint && !historyDetail.llm_runtime_id) return null;

    return (
        <div className="mt-4 rounded-2xl box-muted p-4">
            <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                {t("cockpit.requestDetails.modelInfoTitle")}
            </p>
            <div className="mt-3 grid gap-2 text-xs text-zinc-300 sm:grid-cols-2">
                {(historyDetail.model || historyDetail.llm_model) && (
                    <div className="overflow-hidden">
                        <span className="block truncate text-zinc-500">{t("cockpit.requestDetails.modelLabel")}</span>
                        <div className="text-sm text-zinc-100 truncate" title={historyDetail.model || historyDetail.llm_model || ""}>
                            {historyDetail.model || historyDetail.llm_model}
                        </div>
                    </div>
                )}
                {historyDetail.llm_provider && (
                    <div className="overflow-hidden">
                        <span className="block truncate text-zinc-500">{t("cockpit.requestDetails.providerLabel")}</span>
                        <div className="text-sm text-zinc-100 truncate" title={historyDetail.llm_provider}>
                            {historyDetail.llm_provider}
                        </div>
                    </div>
                )}
                {historyDetail.llm_endpoint && (
                    <div className="overflow-hidden">
                        <span className="block truncate text-zinc-500">{t("cockpit.requestDetails.endpointLabel")}</span>
                        <div className="text-sm text-zinc-100 truncate" title={historyDetail.llm_endpoint}>
                            {historyDetail.llm_endpoint}
                        </div>
                    </div>
                )}
                {historyDetail.llm_runtime_id && (
                    <div className="overflow-hidden">
                        <span className="block truncate text-zinc-500">{t("cockpit.requestDetails.runtimeIdLabel")}</span>
                        <div className="text-sm text-zinc-100 truncate font-mono" title={historyDetail.llm_runtime_id}>
                            {historyDetail.llm_runtime_id.slice(0, 8)}...
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export function TimingSection({
    uiTimingEntry,
    historyDetail,
    llmStartAt,
    t
}: Readonly<{
    uiTimingEntry?: { historyMs?: number; ttftMs?: number } | null;
    historyDetail: HistoryRequestDetail;
    llmStartAt?: string | null;
    t: (key: string, options?: Record<string, string | number>) => string;
}>) {
    return (
        <>
            {uiTimingEntry && (
                <div className="mt-4 rounded-2xl box-muted p-4">
                    <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                        {t("cockpit.requestDetails.uiTimingsTitle")}
                    </p>
                    <div className="mt-2 grid gap-2 text-xs text-zinc-300 sm:grid-cols-2">
                        <div>
                            <span className="text-zinc-400">{t("cockpit.requestDetails.uiTimingHistory")}</span>
                            <div className="text-sm text-white">
                                {uiTimingEntry.historyMs !== undefined ? `${Math.round(uiTimingEntry.historyMs)} ms` : "—"}
                            </div>
                        </div>
                        <div>
                            <span className="text-zinc-400">TTFT (UI)</span>
                            <div className="text-sm text-white">
                                {uiTimingEntry.ttftMs !== undefined ? `${Math.round(uiTimingEntry.ttftMs)} ms` : "—"}
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
                            <div className="text-sm text-white">{formatDateTime(historyDetail.created_at)}</div>
                        </div>
                        <div className="overflow-hidden">
                            <span className="block truncate text-zinc-400" title={t("cockpit.requestDetails.backendTimingsLlmStart")}>
                                {t("cockpit.requestDetails.backendTimingsLlmStart")}
                            </span>
                            <div className="text-sm text-white">{llmStartAt ? formatDateTime(llmStartAt) : "—"}</div>
                        </div>
                        <div className="overflow-hidden">
                            <span className="block truncate text-zinc-400" title={t("cockpit.requestDetails.backendTimingsFirstToken")}>
                                {t("cockpit.requestDetails.backendTimingsFirstToken")}
                            </span>
                            <div className="text-sm text-white">
                                {historyDetail.first_token?.elapsed_ms != null ? `${Math.round(historyDetail.first_token.elapsed_ms)} ms` : "—"}
                            </div>
                        </div>
                        <div className="overflow-hidden">
                            <span className="block truncate text-zinc-400" title={t("cockpit.requestDetails.backendTimingsFirstChunk")}>
                                {t("cockpit.requestDetails.backendTimingsFirstChunk")}
                            </span>
                            <div className="text-sm text-white">
                                {historyDetail.streaming?.first_chunk_ms != null ? `${Math.round(historyDetail.streaming.first_chunk_ms)} ms` : "—"}
                            </div>
                        </div>
                        <div className="overflow-hidden">
                            <span className="block truncate text-zinc-400" title={t("cockpit.requestDetails.backendTimingsChunks")}>
                                {t("cockpit.requestDetails.backendTimingsChunks")}
                            </span>
                            <div className="text-sm text-white">{historyDetail.streaming?.chunk_count ?? "—"}</div>
                        </div>
                        <div className="overflow-hidden">
                            <span className="block truncate text-zinc-400" title={t("cockpit.requestDetails.backendTimingsTotalDuration")}>
                                {t("cockpit.requestDetails.backendTimingsTotalDuration")}
                            </span>
                            <div className="text-sm text-white">{formatDurationSeconds(historyDetail.duration_seconds)}</div>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}

export function FeedbackSection({
    selectedRequestId,
    feedbackByRequest,
    feedbackSubmittingId,
    onFeedbackSubmit,
    onUpdateFeedbackState,
    t
}: Readonly<{
    selectedRequestId: string;
    feedbackByRequest: Record<string, FeedbackState>;
    feedbackSubmittingId: string | null;
    onFeedbackSubmit: (requestId: string, payload?: { rating?: "up" | "down"; comment?: string }) => void;
    onUpdateFeedbackState: (requestId: string, patch: Partial<FeedbackState>) => void;
    t: (key: string, options?: Record<string, string | number>) => string;
}>) {
    const currentFeedback = feedbackByRequest[selectedRequestId];
    return (
        <div className="mt-4 rounded-2xl box-muted p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400">
                <span>{t("cockpit.requestDetails.feedbackTitle")}</span>
            </div>
            <div className="mt-3">
                <div className="flex flex-wrap items-center gap-2">
                    <Button
                        size="xs"
                        variant={currentFeedback?.rating === "up" ? "primary" : "outline"}
                        className={currentFeedback?.rating === "up" ? "border-emerald-500/50 bg-emerald-500/20 text-emerald-100" : ""}
                        onClick={() => {
                            onUpdateFeedbackState(selectedRequestId, { rating: "up", comment: "" });
                            onFeedbackSubmit(selectedRequestId, { rating: "up" });
                        }}
                    >
                        {t("cockpit.requestDetails.feedbackUp")}
                    </Button>
                    <Button
                        size="xs"
                        variant={currentFeedback?.rating === "down" ? "danger" : "outline"}
                        onClick={() => onUpdateFeedbackState(selectedRequestId, { rating: "down" })}
                    >
                        {t("cockpit.requestDetails.feedbackDown")}
                    </Button>
                </div>
                {currentFeedback?.rating === "down" && (
                    <textarea
                        className="mt-3 min-h-[80px] w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-xs text-white outline-none placeholder:text-zinc-500"
                        placeholder={t("cockpit.requestDetails.feedbackPlaceholder")}
                        value={currentFeedback?.comment || ""}
                        onChange={(event) => onUpdateFeedbackState(selectedRequestId, { comment: event.target.value })}
                    />
                )}
                <div className="mt-3 flex flex-wrap items-center gap-2">
                    {currentFeedback?.rating === "down" && (
                        <Button
                            size="xs"
                            variant="outline"
                            disabled={feedbackSubmittingId === selectedRequestId || !(currentFeedback?.comment || "").trim()}
                            onClick={() => onFeedbackSubmit(selectedRequestId)}
                        >
                            {feedbackSubmittingId === selectedRequestId
                                ? t("cockpit.requestDetails.feedbackSubmitting")
                                : t("cockpit.requestDetails.feedbackSubmit")}
                        </Button>
                    )}
                    {currentFeedback?.message && <span className="text-xs text-zinc-400">{currentFeedback.message}</span>}
                </div>
            </div>
        </div>
    );
}

export function LogsSection({ logs, t }: Readonly<{ logs: string[]; t: (key: string, options?: Record<string, string | number>) => string }>) {
    if (!logs || logs.length === 0) return null;
    const logOccurrence = new Map<string, number>();
    const keyedLogs = logs.map((log) => {
        const occurrence = (logOccurrence.get(log) ?? 0) + 1;
        logOccurrence.set(log, occurrence);
        return {
            key: `task-log-${log}-${occurrence}`,
            value: log,
        };
    });

    return (
        <div className="mt-4 rounded-2xl box-muted p-4">
            <div className="flex items-center justify-between">
                <h4 className="heading-h4">{t("cockpit.requestDetails.taskLogsTitle", { count: logs.length })}</h4>
            </div>
            <div className="mt-3 max-h-[180px] space-y-2 overflow-y-auto pr-2 text-xs text-zinc-300">
                {keyedLogs.map((entry) => (
                    <p key={entry.key} className="rounded-xl border border-white/10 bg-white/5 px-3 py-2">
                        {entry.value}
                    </p>
                ))}
            </div>
        </div>
    );
}

export function StepsSection({
    steps,
    requestId,
    copyStepsMessage,
    onCopyDetailSteps,
    t
}: Readonly<{
    steps: HistoryStep[];
    requestId?: string;
    copyStepsMessage: string | null;
    onCopyDetailSteps: () => void;
    t: (key: string, options?: Record<string, string | number>) => string;
}>) {
    return (
        <div className="mt-4 space-y-2 rounded-2xl box-muted p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <h4 className="heading-h4">
                    {t("cockpit.requestDetails.stepsTitle", { count: steps?.length ?? 0 })}
                </h4>
                <div className="flex flex-wrap gap-2 text-xs">
                    {copyStepsMessage && <span className="text-emerald-300">{copyStepsMessage}</span>}
                    <Button variant="outline" size="xs" onClick={onCopyDetailSteps}>
                        {t("cockpit.requestDetails.copyJson")}
                    </Button>
                </div>
            </div>
            <div className="max-h-[45vh] space-y-2 overflow-y-auto pr-2">
                {steps.length === 0 && <p className="text-hint">{t("cockpit.requestDetails.noSteps")}</p>}
                {steps.map((step) => (
                    <div key={`${requestId ?? "request"}-${step.timestamp ?? "no-time"}-${step.component ?? "component"}-${step.action ?? "action"}-${step.status ?? "status"}`} className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm">
                        <div className="flex items-center justify-between">
                            <span className="font-semibold text-white">
                                {step.component || t("cockpit.requestDetails.stepFallback")}
                            </span>
                            {step.status && <Badge tone={statusTone(step.status)}>{step.status}</Badge>}
                        </div>
                        <p className="text-xs text-zinc-400">
                            {step.action || step.details || t("cockpit.requestDetails.stepNoDescription")}
                        </p>
                        {step.timestamp && <p className="text-caption">{formatDateTime(step.timestamp)}</p>}
                    </div>
                ))}
            </div>
        </div>
    );
}
