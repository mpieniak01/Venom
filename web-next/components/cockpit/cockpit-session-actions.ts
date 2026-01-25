"use client";

import { useCallback } from "react";

type CockpitSessionActionsParams = {
  sessionId: string | null;
  resetSession: () => string | null;
  clearSessionMemory: (sessionId: string) => Promise<{ deleted_vectors: number }>;
  clearGlobalMemory: () => Promise<{ deleted_vectors: number }>;
  setMessage: React.Dispatch<React.SetStateAction<string | null>>;
  setMemoryAction: React.Dispatch<React.SetStateAction<null | "session" | "global">>;
  pushToast: (message: string, tone?: "success" | "warning" | "error" | "info") => void;
};

export function useCockpitSessionActions({
  sessionId,
  resetSession,
  clearSessionMemory,
  clearGlobalMemory,
  setMessage,
  setMemoryAction,
  pushToast,
}: CockpitSessionActionsParams) {
  const handleSessionReset = useCallback(() => {
    const newSession = resetSession();
    setMessage(`Nowa sesja chat: ${newSession}`);
  }, [resetSession, setMessage]);

  const handleServerSessionReset = useCallback(async () => {
    if (!sessionId) {
      const newSession = resetSession();
      setMessage(`Nowa sesja chat: ${newSession}`);
      return;
    }
    setMemoryAction("session");
    try {
      await clearSessionMemory(sessionId);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Nie udało się zresetować sesji serwera";
      setMessage(msg);
      return;
    } finally {
      setMemoryAction(null);
    }
    const newSession = resetSession();
    setMessage(`Nowa sesja chat: ${newSession}`);
  }, [clearSessionMemory, resetSession, sessionId, setMemoryAction, setMessage]);

  const handleClearSessionMemory = useCallback(async () => {
    if (!sessionId) return;
    setMemoryAction("session");
    try {
      const resp = await clearSessionMemory(sessionId);
      pushToast(`Wyczyszczono pamięć sesji (${resp.deleted_vectors} wpisów)`, "success");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Nie udało się wyczyścić pamięci sesji";
      setMessage(msg);
    } finally {
      setMemoryAction(null);
    }
  }, [clearSessionMemory, pushToast, sessionId, setMemoryAction, setMessage]);

  const handleClearGlobalMemory = useCallback(async () => {
    setMemoryAction("global");
    try {
      const resp = await clearGlobalMemory();
      pushToast(`Wyczyszczono pamięć globalną (${resp.deleted_vectors} wpisów)`, "success");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Nie udało się wyczyścić pamięci globalnej";
      setMessage(msg);
    } finally {
      setMemoryAction(null);
    }
  }, [clearGlobalMemory, pushToast, setMemoryAction, setMessage]);

  return {
    handleClearGlobalMemory,
    handleClearSessionMemory,
    handleServerSessionReset,
    handleSessionReset,
  };
}
