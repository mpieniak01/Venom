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
  THEME_REGISTRY,
  THEME_STORAGE_KEY,
  isThemeId,
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
    if (isThemeId(stored)) return stored;
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
    return isThemeId(typeof value === "string" ? value : null) ? value : null;
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
  availableThemes: Object.keys(THEME_REGISTRY) as ThemeId[],
});

export function ThemeProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [theme, setThemeState] = useState<ThemeId>(() => resolveInitialTheme());
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
    applyTheme(theme);
  }, [theme]);

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
      setHasLocalOverride(isThemeId(event.newValue));
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
      theme,
      setTheme,
      availableThemes: Object.keys(THEME_REGISTRY) as ThemeId[],
    }),
    [setTheme, theme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}
