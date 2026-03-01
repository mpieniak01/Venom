"use client";

import { useState } from "react";

export function useCockpitQueueActions(input: {
  queuePaused: boolean;
  refreshQueue: () => void;
  refreshTasks: () => void;
  purgeQueueFn: () => Promise<void>;
  emergencyStopFn: () => Promise<{ cancelled: number; purged: number }>;
  toggleQueueFn: (resume: boolean) => Promise<void>;
}) {
  const {
    queuePaused,
    refreshQueue,
    refreshTasks,
    purgeQueueFn,
    emergencyStopFn,
    toggleQueueFn,
  } = input;

  const [queueAction, setQueueAction] = useState<string | null>(null);
  const [queueActionMessage, setQueueActionMessage] = useState<string | null>(null);

  const handleExecuteQueueMutation = async (action: "purge" | "emergency") => {
    if (queueAction) return;
    setQueueAction(action);
    setQueueActionMessage(null);
    try {
      if (action === "purge") {
        await purgeQueueFn();
        setQueueActionMessage("Kolejka została wyczyszczona.");
      } else {
        const res = await emergencyStopFn();
        setQueueActionMessage(
          `Zatrzymano zadania: cancelled ${res.cancelled}, purged ${res.purged}.`
        );
      }
      refreshQueue();
      refreshTasks();
    } catch (err) {
      setQueueActionMessage(
        err instanceof Error ? err.message : "Błąd podczas operacji na kolejce."
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
      setQueueActionMessage(queuePaused ? "Wznowiono kolejkę." : "Wstrzymano kolejkę.");
      refreshQueue();
    } catch (err) {
      setQueueActionMessage(
        err instanceof Error ? err.message : "Błąd sterowania kolejką."
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
