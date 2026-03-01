"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel, StatCard } from "@/components/ui/panel";
import { getTranslatedStatus } from "@/lib/status-helper";
import { statusTone } from "@/lib/status";
import { formatRelativeTime } from "@/lib/date";
import type { HistoryRequest, HistoryStep } from "@/lib/types";
import {
  formatDuration,
  formatErrorDetails,
  formatTimestamp,
  autoFitDiagram,
} from "@/app/inspector/inspector-utils";
import {
  ListFilter,
  Loader2,
  Maximize2,
  Minimize2,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { TransformComponent, TransformWrapper } from "react-zoom-pan-pinch";
import type { MutableRefObject, RefObject } from "react";

type Translator = (key: string, params?: Record<string, string | number>) => string;

type Props = {
  t: Translator;
  selectedId: string | null;
  detailError: string | null;
  flowFullscreen: boolean;
  setFlowFullscreen: (next: boolean) => void;
  svgRef: RefObject<HTMLDivElement | null>;
  fitViewRef: MutableRefObject<(() => void) | null>;
  diagramLoading: boolean;
  mermaidError: string | null;
  reloadMermaid: () => void;
  retrySelect: () => void;
  steps: HistoryStep[];
  stepFilter: string;
  setStepFilter: (value: string) => void;
  contractOnly: boolean;
  setContractOnly: (value: boolean) => void;
  copyMessage: string | null;
  onCopy: () => Promise<void>;
  filteredSteps: HistoryStep[];
  focusedIndex: number | null;
  setFocusedIndex: (value: number | null) => void;
  liveSelectedStatus: string;
  streamConnected: boolean;
  selectedRequest: HistoryRequest | null;
  inspectorFailed: number;
  focusedStep: HistoryStep | null;
};

export function InspectorWorkspace({
  t,
  selectedId,
  detailError,
  flowFullscreen,
  setFlowFullscreen,
  svgRef,
  fitViewRef,
  diagramLoading,
  mermaidError,
  reloadMermaid,
  retrySelect,
  steps,
  stepFilter,
  setStepFilter,
  contractOnly,
  setContractOnly,
  copyMessage,
  onCopy,
  filteredSteps,
  focusedIndex,
  setFocusedIndex,
  liveSelectedStatus,
  streamConnected,
  selectedRequest,
  inspectorFailed,
  focusedStep,
}: Props) {
  return (
    <section className="space-y-6">
      <Panel
        title={t("inspector.panels.diagram.title")}
        action={
          <div className="flex flex-wrap items-center gap-3 text-sm text-zinc-400">
            <div className="flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-3">
              <span>
                {t("inspector.panels.diagram.selected")} <span className="font-semibold text-white">{selectedId ?? "—"}</span>
              </span>
              {detailError && <span className="text-rose-300">{detailError}</span>}
            </div>
            <IconButton
              label={flowFullscreen ? t("inspector.actions.exitFullscreen") : t("inspector.actions.fullscreen")}
              size="xs"
              variant="outline"
              className="border-white/10 text-white"
              icon={flowFullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
              onClick={() => setFlowFullscreen(!flowFullscreen)}
            />
          </div>
        }
      >
        <TransformWrapper wheel={{ step: 0.15 }}>
          {({ zoomIn, zoomOut, resetTransform, setTransform }) => {
            fitViewRef.current = () =>
              autoFitDiagram(svgRef.current, (x, y, scale, duration, easing) =>
                setTransform(x, y, scale, duration, easing as Parameters<typeof setTransform>[4]),
              );
            return (
              <>
                <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
                  <IconButton label={t("inspector.actions.zoomIn")} icon={<ZoomIn className="h-4 w-4" />} onClick={() => zoomIn()} />
                  <IconButton label={t("inspector.actions.zoomOut")} icon={<ZoomOut className="h-4 w-4" />} onClick={() => zoomOut()} />
                  <IconButton label={t("inspector.actions.reset")} icon={<RotateCcw className="h-4 w-4" />} onClick={() => resetTransform()} />
                </div>

                <div className="relative rounded-[28px] box-muted p-4">
                  {diagramLoading && (
                    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 rounded-[28px] bg-black/70 text-sm text-white">
                      <Loader2 className="h-5 w-5 animate-spin text-emerald-300" />
                      {t("inspector.panels.diagram.loading")}
                    </div>
                  )}

                  {mermaidError && (
                    <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 rounded-[28px] bg-black/80 px-6 text-center text-sm text-rose-200">
                      <p>{mermaidError}</p>
                      <Button variant="outline" size="sm" onClick={reloadMermaid}>
                        {t("inspector.actions.tryAgain")}
                      </Button>
                    </div>
                  )}

                  <TransformComponent
                    wrapperStyle={{ width: "100%", height: "100%" }}
                    contentStyle={{ width: "100%", height: "100%" }}
                  >
                    <div className="relative min-h-[700px] w-full">
                      <div
                        ref={svgRef}
                        className="h-full w-full [&>svg]:h-full [&>svg]:w-full [&>svg]:rounded-[20px] [&>svg]:bg-[#020617] [&>svg]:p-4 [&>svg_path]:stroke-[#38bdf8]"
                      />

                      {!selectedId && !diagramLoading && (
                        <div className="absolute inset-0 flex items-center justify-center text-sm text-zinc-500">
                          {t("inspector.panels.diagram.selectHint")}
                        </div>
                      )}

                      {!diagramLoading && (detailError || mermaidError || steps.length === 0) && (
                        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-[28px] bg-black/70 text-center text-sm text-zinc-300">
                          <p>{detailError || mermaidError || t("inspector.panels.diagram.noSteps")}</p>
                          {detailError && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={retrySelect}
                              disabled={!selectedId}
                            >
                              {t("inspector.actions.tryAgain")}
                            </Button>
                          )}
                        </div>
                      )}
                    </div>
                  </TransformComponent>
                </div>
              </>
            );
          }}
        </TransformWrapper>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel
          title={t("inspector.panels.steps.title")}
          description={t("inspector.panels.steps.description")}
          action={
            <div className="flex flex-col gap-2 text-xs sm:flex-row">
              <input
                type="text"
                placeholder={t("inspector.panels.steps.filterPlaceholder")}
                value={stepFilter}
                onChange={(e) => setStepFilter(e.target.value)}
                className="w-full rounded-full border border-white/10 bg-white/5 px-4 py-1 text-white outline-none placeholder:text-zinc-500 focus:border-violet-500/40"
              />
              <label className="pill-badge flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={contractOnly}
                  onChange={(e) => setContractOnly(e.target.checked)}
                />
                {t("inspector.panels.steps.contractsOnly")}
              </label>
              <Button variant="outline" size="sm" onClick={onCopy}>
                {t("inspector.actions.copyJson")}
              </Button>
            </div>
          }
        >
          {copyMessage && <p className="mb-3 text-xs text-emerald-300">{copyMessage}</p>}

          <div className="space-y-3">
            {filteredSteps.length === 0 && (
              <EmptyState
                icon={<ListFilter className="h-4 w-4" />}
                title={t("inspector.panels.steps.emptyTitle")}
                description={t("inspector.panels.steps.emptyDesc")}
                className="text-sm"
              />
            )}

            {filteredSteps.map((step, idx) => (
              <Button
                key={`${selectedId}-${idx}`}
                onClick={() => setFocusedIndex(idx)}
                variant="ghost"
                size="sm"
                className={`list-row w-full text-left text-sm transition ${
                  focusedIndex === idx
                    ? "border-violet-400/60 bg-violet-500/10"
                    : "border-white/10 bg-white/5"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold text-white">{step.component || t("inspector.panels.steps.unknownComponent")}</p>
                    <p className="text-hint">{step.action || step.details || "—"}</p>
                  </div>
                  {step.status && <Badge tone={statusTone(step.status)}>{getTranslatedStatus(step.status, t)}</Badge>}
                </div>
                {step.timestamp && <p className="mt-1 text-caption">{formatTimestamp(step.timestamp)}</p>}
              </Button>
            ))}
          </div>
        </Panel>

        <Panel
          title={t("inspector.panels.details.title")}
          description={t("inspector.panels.details.description")}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <StatCard
              label={t("inspector.panels.details.status")}
              value={liveSelectedStatus}
              hint={
                streamConnected
                  ? t("inspector.panels.details.liveHint")
                  : selectedRequest
                    ? `${t("inspector.panels.details.completedLabel")}: ${formatRelativeTime(selectedRequest.finished_at)}`
                    : t("inspector.panels.diagram.selectHint")
              }
              accent="purple"
            />
            <StatCard
              label={t("inspector.panels.details.executionTime")}
              value={formatDuration(selectedRequest?.duration_seconds ?? null)}
              hint={t("inspector.panels.details.startHint", {
                timestamp: formatTimestamp(selectedRequest?.created_at),
              })}
              accent="blue"
            />
            <StatCard
              label={t("inspector.panels.details.totalSteps")}
              value={steps.length}
              hint={`${t("inspector.latency.stepsFilter")}: ${filteredSteps.length}`}
              accent="green"
            />
            <StatCard
              label={t("inspector.panels.details.failureRate")}
              value={`${inspectorFailed}`}
              hint={t("inspector.panels.details.failureHint")}
              accent="purple"
            />
          </div>

          {selectedRequest?.error_code && (
            <div className="alert alert--error mt-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="danger">{selectedRequest.error_code}</Badge>
                {selectedRequest.error_stage && <Badge tone="neutral">{selectedRequest.error_stage}</Badge>}
                {selectedRequest.error_retryable !== null && selectedRequest.error_retryable !== undefined && (
                  <Badge tone="neutral">retryable: {selectedRequest.error_retryable ? "yes" : "no"}</Badge>
                )}
              </div>
              {selectedRequest.error_message && (
                <p className="mt-2 text-xs text-rose-100">{selectedRequest.error_message}</p>
              )}
              {selectedRequest.error_details && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {formatErrorDetails(selectedRequest.error_details).map((detail) => (
                    <Badge key={detail} tone="neutral">
                      {detail}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="mt-4 rounded-2xl box-base p-4">
            <p className="text-xs uppercase tracking-wide text-zinc-500">{t("inspector.panels.details.selectedStep")}</p>
            <h3 className="heading-h3 mt-2">{focusedStep?.component ?? "—"}</h3>
            <p className="text-sm text-zinc-300">
              {focusedStep?.action || focusedStep?.details || t("inspector.panels.details.clickToView")}
            </p>
            <dl className="mt-3 grid gap-3 text-xs text-zinc-400 sm:grid-cols-2">
              <div>
                <dt className="text-caption">{t("inspector.panels.details.status")}</dt>
                <dd className="text-white">
                  {focusedStep?.status ? getTranslatedStatus(focusedStep.status, t) : "—"}
                </dd>
              </div>
              <div>
                <dt className="text-caption">{t("inspector.panels.details.timestamp")}</dt>
                <dd>{focusedStep?.timestamp ? formatTimestamp(focusedStep.timestamp) : "—"}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-caption">{t("inspector.panels.details.details")}</dt>
                <dd className="text-zinc-300">{focusedStep?.details ?? t("inspector.panels.details.noData")}</dd>
              </div>
            </dl>
            <div className="mt-3">
              <p className="text-caption">{t("inspector.panels.details.stepJson")}</p>
              <div className="mt-2 rounded-2xl box-muted p-3 text-xs text-emerald-50">
                {focusedStep ? (
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap">{JSON.stringify(focusedStep, null, 2)}</pre>
                ) : (
                  <p className="text-hint">{t("inspector.panels.details.clickRaw")}</p>
                )}
              </div>
            </div>
          </div>
        </Panel>
      </div>
    </section>
  );
}
