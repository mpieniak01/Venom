"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { POLLING } from "@/lib/ui-config";
import { createBrowserUuid } from "@/lib/optional-modules/transport";

type SessionContextValue = {
  sessionId: string;
  bootId?: string | null;
  resetSession: () => string;
  setSessionId: (value: string) => void;
};

const SessionContext = createContext<SessionContextValue | null>(null);

const SESSION_ID_KEY = "venom-session-id";
const SESSION_BUILD_KEY = "venom-next-build-id";
const SESSION_BOOT_KEY = "venom-backend-boot-id";

const getBuildId = () => {
  if (globalThis.window === undefined) return "unknown";
  const nextData = (globalThis.window as typeof globalThis.window & { __NEXT_DATA__?: { buildId?: string } })
    .__NEXT_DATA__;
  return nextData?.buildId ?? "unknown";
};

const createSessionId = () => `session-${Date.now()}-${createBrowserUuid().slice(0, 8)}`;

const resolveInitialSessionId = () => {
  if (globalThis.window === undefined) return "";
  try {
    const buildId = getBuildId();
    const storedBuild = globalThis.window.localStorage.getItem(SESSION_BUILD_KEY);
    let storedSession = globalThis.window.localStorage.getItem(SESSION_ID_KEY);
    if (!storedSession || storedBuild !== buildId) {
      storedSession = createSessionId();
      globalThis.window.localStorage.setItem(SESSION_ID_KEY, storedSession);
      globalThis.window.localStorage.setItem(SESSION_BUILD_KEY, buildId);
    }
    return storedSession;
  } catch {
    return createSessionId();
  }
};

export function SessionProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  // The server and first browser render must use the same snapshot. Reading
  // localStorage (or generating an ID) during render breaks hydration.
  const [sessionId, setSessionId] = useState("");
  const sessionRef = useRef("");
  const [backendBootId, setBackendBootId] = useState<string | null>(null);

  const persistSessionId = useCallback((value: string) => {
    sessionRef.current = value;
    setSessionId(value);
    if (globalThis.window === undefined) return;
    try {
      globalThis.window.localStorage.setItem(SESSION_ID_KEY, value);
      globalThis.window.localStorage.setItem(SESSION_BUILD_KEY, getBuildId());
    } catch {
      // ignore storage issues
    }
  }, []);

  useEffect(() => {
    // Preserve an explicit reset/select that happened before initialization and
    // avoid generating two IDs when StrictMode replays the effect.
    if (!sessionRef.current) persistSessionId(resolveInitialSessionId());
  }, [persistSessionId]);

  const resetSession = useCallback(() => {
    const next = createSessionId();
    persistSessionId(next);
    return next;
  }, [persistSessionId]);

  useEffect(() => {
    if (globalThis.window === undefined) return;
    let active = true;
    let syncing = false;
    const syncBootId = async () => {
      if (!active || syncing || document.visibilityState === "hidden") return;
      syncing = true;
      try {
        const response = await fetch("/api/v1/system/status");
        if (!response.ok) return;
        const data = (await response.json()) as { boot_id?: string };
        const bootId = data.boot_id;
        if (!active || typeof bootId !== "string" || !bootId) return;
        setBackendBootId(bootId);
        const storedBoot = globalThis.window.localStorage.getItem(SESSION_BOOT_KEY);
        if (!storedBoot) {
          globalThis.window.localStorage.setItem(SESSION_BOOT_KEY, bootId);
          return;
        }
        if (storedBoot !== bootId) {
          const nextSession = createSessionId();
          globalThis.window.localStorage.setItem(SESSION_ID_KEY, nextSession);
          globalThis.window.localStorage.setItem(SESSION_BUILD_KEY, getBuildId());
          globalThis.window.localStorage.setItem(SESSION_BOOT_KEY, bootId);
          if (active) {
            persistSessionId(nextSession);
          }
        }
      } catch {
        // ignore fetch failures
      } finally {
        syncing = false;
      }
    };
    void syncBootId();
    const handleFocus = () => {
      void syncBootId();
    };
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        void syncBootId();
      }
    };
    globalThis.window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibility);
    const interval = globalThis.window.setInterval(syncBootId, POLLING.BOOT_SYNC_INTERVAL_MS);
    return () => {
      active = false;
      globalThis.window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibility);
      globalThis.window.clearInterval(interval);
    };
  }, [persistSessionId]);

  const value = useMemo(
    () => ({
      sessionId,
      bootId: backendBootId,
      resetSession,
      setSessionId: persistSessionId,
    }),
    [sessionId, backendBootId, resetSession, persistSessionId],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useOptionalSession() {
  return useContext(SessionContext);
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error("useSession must be used within SessionProvider");
  }
  return ctx;
}
