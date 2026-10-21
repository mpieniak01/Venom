"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { POLLING } from "@/lib/ui-config";
import { createBrowserUuid } from "@/lib/optional-modules/transport";

type SessionContextValue = {
  sessionId: string;
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
  const [sessionId, setSessionId] = useState<string>(() => resolveInitialSessionId());

  const persistSessionId = useCallback((value: string) => {
    setSessionId(value);
    if (globalThis.window === undefined) return;
    try {
      globalThis.window.localStorage.setItem(SESSION_ID_KEY, value);
      globalThis.window.localStorage.setItem(SESSION_BUILD_KEY, getBuildId());
    } catch {
      // ignore storage issues
    }
  }, []);

  const resetSession = useCallback(() => {
    const next = createSessionId();
    persistSessionId(next);
    return next;
  }, [persistSessionId]);

  useEffect(() => {
    if (globalThis.window === undefined) return;
    let active = true;
    const syncBootId = async () => {
      try {
        const response = await fetch("/api/v1/system/status");
        if (!response.ok) return;
        const data = (await response.json()) as { boot_id?: string };
        const bootId = data.boot_id;
        if (!bootId) return;
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
            setSessionId(nextSession);
          }
        }
      } catch {
        // ignore fetch failures
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
    globalThis.window.addEventListener("visibilitychange", handleVisibility);
    const interval = globalThis.window.setInterval(syncBootId, POLLING.BOOT_SYNC_INTERVAL_MS);
    return () => {
      active = false;
      globalThis.window.removeEventListener("focus", handleFocus);
      globalThis.window.removeEventListener("visibilitychange", handleVisibility);
      globalThis.window.clearInterval(interval);
    };
  }, []);

  const value = useMemo(
    () => ({
      sessionId,
      resetSession,
      setSessionId: persistSessionId,
    }),
    [sessionId, resetSession, persistSessionId],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error("useSession must be used within SessionProvider");
  }
  return ctx;
}
