"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { POLLING } from "@/lib/ui-config";

type SessionContextValue = {
  sessionId: string;
  resetSession: () => string;
  setSessionId: (value: string) => void;
};

const SessionContext = createContext<SessionContextValue | null>(null);

const SESSION_ID_KEY = "venom-session-id";
const SESSION_BUILD_KEY = "venom-next-build-id";
const SESSION_BOOT_KEY = "venom-backend-boot-id";
let sessionIdFallbackCounter = 0;

const getBuildId = () => {
  if (globalThis.window === undefined) return "unknown";
  const nextData = (globalThis.window as typeof globalThis.window & { __NEXT_DATA__?: { buildId?: string } })
    .__NEXT_DATA__;
  return nextData?.buildId ?? "unknown";
};

const createSessionId = () => {
  const rand = (() => {
    const webCrypto: Crypto | undefined = globalThis.crypto;

    if (webCrypto?.randomUUID) {
      return webCrypto.randomUUID().slice(0, 8);
    }
    if (webCrypto?.getRandomValues) {
      const bytes = new Uint8Array(4);
      webCrypto.getRandomValues(bytes);
      return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
    }
    sessionIdFallbackCounter += 1;
    return `${Date.now().toString(36)}${sessionIdFallbackCounter.toString(36)}`.slice(-12);
  })();
  return `session-${Date.now()}-${rand}`;
};

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [sessionId, setSessionIdState] = useState<string>("");

  const setSessionId = useCallback((value: string) => {
    setSessionIdState(value);
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
    setSessionId(next);
    return next;
  }, [setSessionId]);

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
            setSessionIdState(nextSession);
          }
        }
      } catch {
        // ignore fetch failures
      }
    };
    try {
      const buildId = getBuildId();
      const storedBuild = globalThis.window.localStorage.getItem(SESSION_BUILD_KEY);
      let storedSession = globalThis.window.localStorage.getItem(SESSION_ID_KEY);
      if (!storedSession || storedBuild !== buildId) {
        storedSession = createSessionId();
        globalThis.window.localStorage.setItem(SESSION_ID_KEY, storedSession);
        globalThis.window.localStorage.setItem(SESSION_BUILD_KEY, buildId);
      }
      setSessionIdState(storedSession);
    } catch {
      setSessionIdState(createSessionId());
    }
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
