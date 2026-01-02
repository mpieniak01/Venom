"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

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
  if (typeof window === "undefined") return "unknown";
  const nextData = (window as typeof window & { __NEXT_DATA__?: { buildId?: string } })
    .__NEXT_DATA__;
  return nextData?.buildId ?? "unknown";
};

const createSessionId = () => `session-${Date.now()}`;

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [sessionId, setSessionIdState] = useState<string>("");

  const setSessionId = useCallback((value: string) => {
    setSessionIdState(value);
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(SESSION_ID_KEY, value);
      window.localStorage.setItem(SESSION_BUILD_KEY, getBuildId());
    } catch {
      // ignore storage issues
    }
  }, []);

  const resetSession = useCallback(() => {
    const next = createSessionId();
    setSessionId(next);
    return next;
  }, [setSessionId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    let active = true;
    try {
      const buildId = getBuildId();
      const storedBuild = window.localStorage.getItem(SESSION_BUILD_KEY);
      let storedSession = window.localStorage.getItem(SESSION_ID_KEY);
      if (!storedSession || storedBuild !== buildId) {
        storedSession = createSessionId();
        window.localStorage.setItem(SESSION_ID_KEY, storedSession);
        window.localStorage.setItem(SESSION_BUILD_KEY, buildId);
      }
      setSessionIdState(storedSession);
    } catch {
      setSessionIdState(createSessionId());
    }
    (async () => {
      try {
        const response = await fetch("/api/v1/system/status");
        if (!response.ok) return;
        const data = (await response.json()) as { boot_id?: string };
        const bootId = data.boot_id;
        if (!bootId) return;
        const storedBoot = window.localStorage.getItem(SESSION_BOOT_KEY);
        if (!storedBoot) {
          window.localStorage.setItem(SESSION_BOOT_KEY, bootId);
          return;
        }
        if (storedBoot !== bootId) {
          const nextSession = createSessionId();
          window.localStorage.setItem(SESSION_ID_KEY, nextSession);
          window.localStorage.setItem(SESSION_BUILD_KEY, getBuildId());
          window.localStorage.setItem(SESSION_BOOT_KEY, bootId);
          if (active) {
            setSessionIdState(nextSession);
          }
        }
      } catch {
        // ignore fetch failures
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const value = useMemo(
    () => ({
      sessionId,
      resetSession,
      setSessionId,
    }),
    [sessionId, resetSession, setSessionId],
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
