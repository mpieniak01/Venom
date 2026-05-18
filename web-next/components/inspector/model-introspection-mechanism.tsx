"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { Badge } from "@/components/ui/badge";
import { useTranslation } from "@/lib/i18n";
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
  try {
    const localStorage = globalThis.window?.localStorage;
    if (!localStorage) return true;
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) {
      return true;
    }
    return raw === "true";
  } catch {
    return true;
  }
}

function subscribe(listener: () => void): () => void {
  const windowRef = globalThis.window;
  if (!windowRef) return () => undefined;
  const handleStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) {
      listener();
    }
  };
  const handleCustomEvent = () => listener();
  windowRef.addEventListener("storage", handleStorage);
  windowRef.addEventListener(STORE_EVENT, handleCustomEvent);
  return () => {
    windowRef.removeEventListener("storage", handleStorage);
    windowRef.removeEventListener(STORE_EVENT, handleCustomEvent);
  };
}

function writeEnabledToStorage(enabled: boolean) {
  const windowRef = globalThis.window;
  const localStorage = windowRef?.localStorage;
  if (!windowRef || !localStorage) return;
  try {
    localStorage.setItem(STORAGE_KEY, enabled ? "true" : "false");
    windowRef.dispatchEvent(new Event(STORE_EVENT));
  } catch {
    // Storage may be blocked (privacy mode); keep UI responsive.
  }
}

export function ModelIntrospectionMechanismProvider({
  children,
}: Readonly<{ children: ReactNode }>) {
  const enabled = useSyncExternalStore(
    subscribe,
    readEnabledFromStorage,
    () => false,
  );

  const setMechanismEnabled = useCallback((nextEnabled: boolean) => {
    writeEnabledToStorage(nextEnabled);
  }, []);

  const toggle = useCallback(() => {
    writeEnabledToStorage(!enabled);
  }, [enabled]);

  const value = useMemo(
    () => ({
      enabled,
      setEnabled: setMechanismEnabled,
      toggle,
    }),
    [enabled, setMechanismEnabled, toggle],
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
  const t = useTranslation();
  const { enabled, setEnabled } = useModelIntrospectionMechanism();
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setHydrated(true);
  }, []);

  const displayEnabled = hydrated ? enabled : false;
  const label = displayEnabled ? t("inspector.modelIntrospection.mechanism.enabled") : t("inspector.modelIntrospection.mechanism.disabled");

  if (variant === "compact") {
    return (
      <div
        className={cn(
          "hidden items-center gap-2 rounded-full border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-3 py-2 text-xs text-[color:var(--text-primary)] xl:inline-flex",
          className,
        )}
      >
        <span className="uppercase tracking-[0.28em] text-[color:var(--ui-muted)]">{t("inspector.modelIntrospection.mechanism.analysisLabel")}</span>
        <Badge tone={displayEnabled ? "success" : "neutral"}>{label}</Badge>
        <Switch
          checked={displayEnabled}
          onCheckedChange={setEnabled}
          aria-label={t("inspector.modelIntrospection.mechanism.toggleAria")}
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
        <p className="text-xs uppercase tracking-wide text-zinc-500">{t("inspector.modelIntrospection.mechanism.title")}</p>
        <p className="text-sm text-zinc-200">
          {t("inspector.modelIntrospection.mechanism.description")}
        </p>
      </div>
      <div className="flex items-center gap-3">
        <Badge tone={displayEnabled ? "success" : "neutral"}>{label}</Badge>
        <Switch
          checked={displayEnabled}
          onCheckedChange={setEnabled}
          aria-label={t("inspector.modelIntrospection.mechanism.toggleAria")}
        />
      </div>
    </div>
  );
}
