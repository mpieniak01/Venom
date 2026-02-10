"use client";

import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

import {
  extractRuntimeContext,
  parseRuntimeErrorMeta,
  parseSimpleResponse,
  resolveRequestModeLabel,
  ContextPreviewMeta,
  FeedbackState,
} from "./drawer-helpers";

import {
  PromptSection,
  PayloadSection,
  DiagnosticsSection,
  ModelInfoSection,
  TimingSection,
  FeedbackSection,
  LogsSection,
  StepsSection,
} from "./drawer-sections";

import type { HistoryRequestDetail, Task } from "@/lib/types";

type CockpitRequestDetailDrawerProps = Readonly<{
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
}>;

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
  const requestModeLabel = useMemo(
    () => resolveRequestModeLabel(contextPreviewMeta, historyDetail),
    [contextPreviewMeta, historyDetail],
  );

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
          <p className="text-sm text-zinc-500">{t("cockpit.requestDetails.emptyHint")}</p>
        )}
        {loadingHistory && <p className="text-sm text-zinc-400">{t("cockpit.requestDetails.loading")}</p>}
        {historyError && <p className="text-sm text-rose-300">{historyError}</p>}

        {historyDetail && (
          <>
            <PromptSection prompt={historyDetail.prompt} t={t} />

            <PayloadSection
              payloadSessionMeta={payloadSessionMeta}
              payloadForcedRoute={payloadForcedRoute}
              payloadGenerationParams={payloadGenerationParams}
              payloadContextUsed={payloadContextUsed}
              contextPreviewMeta={contextPreviewMeta}
              t={t}
            />

            <DiagnosticsSection
              requestModeLabel={requestModeLabel}
              simpleResponse={simpleResponse}
              runtimeErrorMeta={runtimeErrorMeta}
              t={t}
            />

            <ModelInfoSection historyDetail={historyDetail} t={t} />

            <TimingSection
              uiTimingEntry={uiTimingEntry}
              historyDetail={historyDetail}
              llmStartAt={llmStartAt}
              t={t}
            />

            {selectedRequestId && (
              <FeedbackSection
                selectedRequestId={selectedRequestId}
                feedbackByRequest={feedbackByRequest}
                feedbackSubmittingId={feedbackSubmittingId}
                onFeedbackSubmit={onFeedbackSubmit}
                onUpdateFeedbackState={onUpdateFeedbackState}
                t={t}
              />
            )}

            <LogsSection logs={selectedTask?.logs || []} t={t} />

            <StepsSection
              steps={historyDetail.steps || []}
              requestId={historyDetail.request_id}
              copyStepsMessage={copyStepsMessage}
              onCopyDetailSteps={onCopyDetailSteps}
              t={t}
            />

            <div className="mt-4 flex flex-wrap gap-2 text-xs">
              <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
                {t("cockpit.requestDetails.close")}
              </Button>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
