"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { NOTIFICATIONS } from "@/lib/ui-config";

type ToastTone = "success" | "error" | "warning" | "info";

type ToastEntry = {
  id: string;
  message: string;
  tone: ToastTone;
};

type ToastContextValue = {
  pushToast: (message: string, tone?: ToastTone) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const toneStyles: Record<ToastTone, string> = {
  success: "border-emerald-400/40 bg-emerald-500/10 text-emerald-100",
  error: "border-rose-400/40 bg-rose-500/10 text-rose-100",
  warning: "border-amber-400/40 bg-amber-500/10 text-amber-100",
  info: "border-sky-400/40 bg-sky-500/10 text-sky-100",
};

let toastIdFallbackCounter = 0;

const createToastId = () => {
  if (typeof crypto !== "undefined" && "getRandomValues" in crypto) {
    const bytes = new Uint8Array(8);
    crypto.getRandomValues(bytes);
    const randomHex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
    return `${Date.now()}-${randomHex}`;
  }
  toastIdFallbackCounter += 1;
  return `${Date.now()}-${toastIdFallbackCounter.toString(16).padStart(4, "0")}`;
};

export function ToastProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const timersRef = useRef<Map<string, number>>(new Map());

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      globalThis.clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const pushToast = useCallback(
    (message: string, tone: ToastTone = "success") => {
      const id = createToastId();
      setToasts((prev) => [...prev, { id, message, tone }]);
      const timer = globalThis.setTimeout(() => removeToast(id), NOTIFICATIONS.TOAST_TIMEOUT_MS);
      timersRef.current.set(id, timer);
    },
    [removeToast],
  );

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((timer) => globalThis.clearTimeout(timer));
      timers.clear();
    };
  }, []);

  const value = useMemo(() => ({ pushToast }), [pushToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed right-6 top-20 z-50 flex w-[320px] flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cn(
              "pointer-events-auto rounded-2xl border px-3 py-2 text-xs shadow-card backdrop-blur",
              toneStyles[toast.tone],
            )}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return context;
}
