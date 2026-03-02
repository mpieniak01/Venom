"use client";

import {
  useCallback,
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  DEFAULT_THEME,
  THEME_IDS,
  THEME_STORAGE_KEY,
  resolveThemeId,
  normalizeTheme,
  type ThemeId,
  } from "./theme-registry";

export type { ThemeId } from "./theme-registry";

const RUNTIME_CONFIG_ENDPOINT = "/api/v1/config/runtime";
const BACKEND_THEME_KEY = "UI_THEME_DEFAULT";

function resolveStoredTheme(): ThemeId | null {
  if (globalThis.window === undefined) return null;
  try {
    const stored = globalThis.window.localStorage.getItem(THEME_STORAGE_KEY);
    const resolved = resolveThemeId(stored);
    if (resolved) {
      if (stored !== resolved) {
        globalThis.window.localStorage.setItem(THEME_STORAGE_KEY, resolved);
      }
      return resolved;
    }
    if (stored) {
      globalThis.window.localStorage.removeItem(THEME_STORAGE_KEY);
    }
    return null;
  } catch {
    return null;
  }
}

export function resolveInitialTheme(): ThemeId {
  return resolveStoredTheme() ?? DEFAULT_THEME;
}

function applyTheme(theme: ThemeId) {
  if (globalThis.window === undefined) return;
  document.documentElement.dataset.theme = theme;
}

async function fetchBackendDefaultTheme(): Promise<ThemeId | null> {
  try {
    const response = await fetch(RUNTIME_CONFIG_ENDPOINT, { cache: "no-store" });
    if (!response.ok) return null;
    const data = (await response.json()) as {
      status?: string;
      config?: Record<string, unknown>;
    };
    if (data.status !== "success") return null;
    const value = data.config?.[BACKEND_THEME_KEY];
    const candidate = typeof value === "string" ? value : null;
    const resolved = resolveThemeId(candidate);
    if (!resolved) return null;
    if (candidate !== resolved) {
      void syncBackendThemePreference(resolved);
    }
    return resolved;
  } catch {
    return null;
  }
}

async function syncBackendThemePreference(theme: ThemeId): Promise<void> {
  try {
    await fetch(RUNTIME_CONFIG_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ updates: { [BACKEND_THEME_KEY]: theme } }),
    });
  } catch {
    // Best-effort sync only.
  }
}

type ThemeContextValue = {
  theme: ThemeId;
  setTheme: (theme: ThemeId) => void;
  availableThemes: ThemeId[];
};

const ThemeContext = createContext<ThemeContextValue>({
  theme: DEFAULT_THEME,
  setTheme: () => {},
  availableThemes: THEME_IDS,
});

export function ThemeProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [themeState, setThemeState] = useState<ThemeId>(() => resolveInitialTheme());
  const [hasLocalOverride, setHasLocalOverride] = useState<boolean>(
    () => resolveStoredTheme() !== null,
  );

  const setTheme = useCallback((nextTheme: ThemeId) => {
    setThemeState(nextTheme);
    setHasLocalOverride(true);
    if (globalThis.window !== undefined) {
      try {
        globalThis.window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
      } catch {
        // Ignore storage errors, fallback to in-memory state.
      }
    }
    void syncBackendThemePreference(nextTheme);
  }, []);

  useEffect(() => {
    applyTheme(themeState);
  }, [themeState]);

  useEffect(() => {
    if (hasLocalOverride) return;
    let cancelled = false;
    void fetchBackendDefaultTheme().then((backendTheme) => {
      if (cancelled || hasLocalOverride || !backendTheme) return;
      setThemeState(backendTheme);
    });
    return () => {
      cancelled = true;
    };
  }, [hasLocalOverride]);

  useEffect(() => {
    if (globalThis.window === undefined) return;
    const onStorage = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY) return;
      const next = normalizeTheme(event.newValue);
      setThemeState(next);
      setHasLocalOverride(resolveThemeId(event.newValue) !== null);
    };
    globalThis.window.addEventListener("storage", onStorage);
    return () => {
      globalThis.window.removeEventListener("storage", onStorage);
    };
  }, []);

  useEffect(() => {
    if (hasLocalOverride) return;
    if (globalThis.window === undefined) return;
    try {
      globalThis.window.localStorage.removeItem(THEME_STORAGE_KEY);
    } catch {
      // Ignore storage errors.
    }
  }, [hasLocalOverride]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme: themeState,
      setTheme,
      availableThemes: THEME_IDS,
    }),
    [setTheme, themeState],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}
