"use client";

import { useState } from "react";

export function useCockpitQueueActions(input: {
  queuePaused: boolean;
  refreshQueue: () => void | Promise<void>;
  refreshTasks: () => void | Promise<void>;
  purgeQueueFn: () => Promise<void>;
  emergencyStopFn: () => Promise<{ cancelled: number; purged: number }>;
  toggleQueueFn: (resume: boolean) => Promise<void>;
  t: (key: string, replacements?: Record<string, string | number>) => string;
}) {
  const {
    queuePaused,
    refreshQueue,
    refreshTasks,
    purgeQueueFn,
    emergencyStopFn,
    toggleQueueFn,
    t,
  } = input;

  const triggerRefresh = (refreshFn: () => void | Promise<void>, context: string) => {
    Promise.resolve(refreshFn()).catch((error) => {
      console.error(`${context}:`, error);
    });
  };

  const [queueAction, setQueueAction] = useState<string | null>(null);
  const [queueActionMessage, setQueueActionMessage] = useState<string | null>(null);

  const handleExecuteQueueMutation = async (action: "purge" | "emergency") => {
    if (queueAction) return;
    setQueueAction(action);
    setQueueActionMessage(null);
    try {
      if (action === "purge") {
        await purgeQueueFn();
        setQueueActionMessage(t("cockpit.queueActions.queuePurged"));
      } else {
        const res = await emergencyStopFn();
        setQueueActionMessage(
          t("cockpit.queueActions.emergencyStopped", {
            cancelled: res.cancelled,
            purged: res.purged,
          }),
        );
      }
      triggerRefresh(refreshQueue, "Queue refresh failed");
      triggerRefresh(refreshTasks, "Tasks refresh failed");
    } catch (err) {
      setQueueActionMessage(
        err instanceof Error ? err.message : t("cockpit.queueActions.operationError"),
      );
    } finally {
      setQueueAction(null);
    }
  };

  const handleToggleQueue = async () => {
    if (queueAction) return;
    const action = queuePaused ? "resume" : "pause";
    setQueueAction(action);
    setQueueActionMessage(null);
    try {
      await toggleQueueFn(queuePaused);
      setQueueActionMessage(
        queuePaused
          ? t("cockpit.queueActions.queueResumed")
          : t("cockpit.queueActions.queuePaused"),
      );
      triggerRefresh(refreshQueue, "Queue refresh failed");
    } catch (err) {
      setQueueActionMessage(
        err instanceof Error ? err.message : t("cockpit.queueActions.toggleError"),
      );
    } finally {
      setQueueAction(null);
    }
  };

  return {
    queueAction,
    queueActionMessage,
    handleExecuteQueueMutation,
    handleToggleQueue,
  };
}
