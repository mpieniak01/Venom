"use client";

import { useCallback } from "react";
import type { HistoryRequestDetail, Task } from "@/lib/types";
import { NOTIFICATIONS } from "@/lib/ui-config";

type RequestDetailActionsParams = {
  findTaskMatch: (requestId?: string, prompt?: string | null) => Task | null;
  simpleRequestDetails: Record<string, HistoryRequestDetail>;
  fetchHistoryDetail: (requestId: string) => Promise<HistoryRequestDetail>;
  fetchTaskDetail: (requestId: string) => Promise<Task>;
  setSelectedRequestId: React.Dispatch<React.SetStateAction<string | null>>;
  setDetailOpen: React.Dispatch<React.SetStateAction<boolean>>;
  setHistoryDetail: React.Dispatch<React.SetStateAction<HistoryRequestDetail | null>>;
  setHistoryError: React.Dispatch<React.SetStateAction<string | null>>;
  setCopyStepsMessage: React.Dispatch<React.SetStateAction<string | null>>;
  setSelectedTask: React.Dispatch<React.SetStateAction<Task | null>>;
  setLoadingHistory: React.Dispatch<React.SetStateAction<boolean>>;
  historyDetail: HistoryRequestDetail | null;
};

export function useCockpitRequestDetailActions({
  findTaskMatch,
  simpleRequestDetails,
  fetchHistoryDetail,
  fetchTaskDetail,
  setSelectedRequestId,
  setDetailOpen,
  setHistoryDetail,
  setHistoryError,
  setCopyStepsMessage,
  setSelectedTask,
  setLoadingHistory,
  historyDetail,
}: RequestDetailActionsParams) {
  const openRequestDetail = useCallback(async (requestId: string, prompt?: string) => {
    setSelectedRequestId(requestId);
    setDetailOpen(true);
    setHistoryDetail(null);
    setHistoryError(null);
    setCopyStepsMessage(null);
    setSelectedTask(null);
    const localSimple = simpleRequestDetails[requestId];
    if (localSimple) {
      setHistoryDetail(localSimple);
      setLoadingHistory(false);
      return;
    }
    setLoadingHistory(true);
    const fallback = findTaskMatch(requestId, prompt);
    try {
      const [detailResult, taskResult] = await Promise.allSettled([
        fetchHistoryDetail(requestId),
        fetchTaskDetail(requestId),
      ]);

      if (detailResult.status === "fulfilled") {
        setHistoryDetail(detailResult.value);
      } else {
        setHistoryError(
          detailResult.reason instanceof Error
            ? detailResult.reason.message
            : "Nie udało się pobrać szczegółów",
        );
      }

      if (taskResult.status === "fulfilled") {
        setSelectedTask(taskResult.value);
      } else if (fallback) {
        setSelectedTask(fallback);
      }
    } catch (err) {
      setHistoryError(
        err instanceof Error ? err.message : "Nie udało się pobrać szczegółów",
      );
      if (fallback) {
        setSelectedTask(fallback);
      }
    } finally {
      setLoadingHistory(false);
    }
  }, [
    fetchHistoryDetail,
    fetchTaskDetail,
    findTaskMatch,
    setCopyStepsMessage,
    setDetailOpen,
    setHistoryDetail,
    setHistoryError,
    setLoadingHistory,
    setSelectedRequestId,
    setSelectedTask,
    simpleRequestDetails,
  ]);

  const handleCopyDetailSteps = useCallback(async () => {
    if (!historyDetail?.steps || historyDetail.steps.length === 0) {
      setCopyStepsMessage("Brak danych do skopiowania.");
      setTimeout(() => setCopyStepsMessage(null), NOTIFICATIONS.COPY_MESSAGE_TIMEOUT_MS);
      return;
    }
    try {
      await navigator.clipboard.writeText(JSON.stringify(historyDetail.steps, null, 2));
      setCopyStepsMessage("Skopiowano kroki.");
    } catch (err) {
      console.error("Clipboard error:", err);
      setCopyStepsMessage("Nie udało się skopiować.");
    } finally {
      setTimeout(() => setCopyStepsMessage(null), NOTIFICATIONS.COPY_MESSAGE_TIMEOUT_MS);
    }
  }, [historyDetail?.steps, setCopyStepsMessage]);

  return { handleCopyDetailSteps, openRequestDetail };
}
