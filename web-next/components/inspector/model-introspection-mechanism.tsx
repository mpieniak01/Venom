"use client";

import { createContext, useCallback, useContext, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "venom.modelIntrospection.liveAnalysisEnabled";
const STORE_EVENT = "venom:model-introspection-mechanism-change";

type ModelIntrospectionMechanismContextValue = {
  enabled: boolean;
  setEnabled: (enabled: boolean) => void;
  toggle: () => void;
};

const ModelIntrospectionMechanismContext = createContext<ModelIntrospectionMechanismContextValue | null>(null);

function readEnabledFromStorage(): boolean {
  if (globalThis.window === undefined) return false;
  return globalThis.window.localStorage.getItem(STORAGE_KEY) === "true";
}

function subscribe(listener: () => void): () => void {
  if (globalThis.window === undefined) return () => undefined;
  const handleStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) {
      listener();
    }
  };
  const handleCustomEvent = () => listener();
  globalThis.window.addEventListener("storage", handleStorage);
  globalThis.window.addEventListener(STORE_EVENT, handleCustomEvent);
  return () => {
    globalThis.window.removeEventListener("storage", handleStorage);
    globalThis.window.removeEventListener(STORE_EVENT, handleCustomEvent);
  };
}

function writeEnabledToStorage(enabled: boolean) {
  if (globalThis.window === undefined) return;
  globalThis.window.localStorage.setItem(STORAGE_KEY, enabled ? "true" : "false");
  globalThis.window.dispatchEvent(new Event(STORE_EVENT));
}

export function ModelIntrospectionMechanismProvider({
  children,
}: Readonly<{ children: ReactNode }>) {
  const enabled = useSyncExternalStore(subscribe, readEnabledFromStorage, () => false);

  const setEnabled = useCallback((nextEnabled: boolean) => {
    writeEnabledToStorage(nextEnabled);
  }, []);

  const toggle = useCallback(() => {
    writeEnabledToStorage(!readEnabledFromStorage());
  }, []);

  const value = useMemo(
    () => ({
      enabled,
      setEnabled,
      toggle,
    }),
    [enabled, setEnabled, toggle],
  );

  return (
    <ModelIntrospectionMechanismContext.Provider value={value}>
      {children}
    </ModelIntrospectionMechanismContext.Provider>
  );
}

export function useModelIntrospectionMechanism() {
  const value = useContext(ModelIntrospectionMechanismContext);
  if (!value) {
    throw new Error("useModelIntrospectionMechanism must be used within ModelIntrospectionMechanismProvider");
  }
  return value;
}

type ModelIntrospectionMechanismControlProps = {
  variant?: "compact" | "panel";
  className?: string;
};

export function ModelIntrospectionMechanismControl({
  variant = "panel",
  className,
}: Readonly<ModelIntrospectionMechanismControlProps>) {
  const { enabled, setEnabled } = useModelIntrospectionMechanism();
  const label = enabled ? "enabled" : "disabled";

  if (variant === "compact") {
    return (
      <div
        className={cn(
          "hidden items-center gap-2 rounded-full border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-3 py-2 text-xs text-[color:var(--text-primary)] xl:inline-flex",
          className,
        )}
      >
        <span className="uppercase tracking-[0.28em] text-[color:var(--ui-muted)]">Analysis</span>
        <Badge tone={enabled ? "success" : "neutral"}>{label}</Badge>
        <Switch
          checked={enabled}
          onCheckedChange={setEnabled}
          aria-label="Toggle live analysis mechanism"
        />
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/10 bg-white/5 px-4 py-4",
        className,
      )}
    >
      <div className="space-y-1">
        <p className="text-xs uppercase tracking-wide text-zinc-500">Mechanism</p>
        <p className="text-sm text-zinc-200">
          Shared live analysis switch used by Inspector, sidebar and TopBar. Disabled by default to keep the stack light.
        </p>
      </div>
      <div className="flex items-center gap-3">
        <Badge tone={enabled ? "success" : "neutral"}>{label}</Badge>
        <Switch
          checked={enabled}
          onCheckedChange={setEnabled}
          aria-label="Toggle live analysis mechanism"
        />
      </div>
    </div>
  );
}
