"use client";

import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
  type ReactNode,
} from "react";
import dayjs from "dayjs";
import { pl } from "./locales/pl";
import { loadDateLocale, loadLocale } from "./load-locale";
import {
  isLanguageCode, languageFromCookie, languageFromHeader,
  LANGUAGE_COOKIE, LANGUAGE_STORAGE_KEY,
  type LanguageCode, type LocaleDictionary,
} from "./preferences";
export type { LanguageCode, LocaleDictionary } from "./preferences";

type LanguageContextValue = {
  language: LanguageCode;
  setLanguage: (code: LanguageCode) => void;
  t: (path: string, replacements?: Record<string, string | number>) => string;
};

const LanguageContext = createContext<LanguageContextValue>({
  language: "pl",
  setLanguage: () => {},
  t: (path: string) => resolvePath(pl, path) ?? path,
});

function resolvePath(locale: LocaleDictionary, path: string): string | null {
  const result = path.split(".").reduce<unknown>((acc, part) => {
    if (acc && typeof acc === "object" && part in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[part];
    }
    return undefined;
  }, locale);
  return typeof result === "string" ? result : null;
}

function applyReplacements(value: string, replacements?: Record<string, string | number>) {
  if (!replacements) return value;
  return value.replace(/\{\{\s*([^{}]+?)\s*\}\}/g, (placeholder, key: string) =>
    Object.hasOwn(replacements, key) ? String(replacements[key]) : placeholder,
  );
}

function preferredLanguage(): LanguageCode {
  try {
    const stored = globalThis.window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (isLanguageCode(stored)) return stored;
  } catch {
    // A denied localStorage must not make the entire shell unusable.
  }
  return languageFromCookie(document.cookie) ??
    languageFromHeader(globalThis.window.navigator.language);
}

function persistLanguage(language: LanguageCode) {
  try { globalThis.window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language); } catch {}
  document.cookie = `${LANGUAGE_COOKIE}=${language}; Path=/; Max-Age=31536000; SameSite=Lax${globalThis.window.location.protocol === "https:" ? "; Secure" : ""}`;
}

type LanguageProviderProps = Readonly<{
  children: ReactNode;
  initialLanguage?: LanguageCode;
  initialDictionary?: LocaleDictionary;
  loadDictionary?: typeof loadLocale;
}>;

export function LanguageProvider({
  children, initialLanguage = "pl", initialDictionary = pl, loadDictionary = loadLocale,
}: LanguageProviderProps) {
  // Server and first client render use the same dictionary. A stored legacy
  // preference is migrated after hydration; subsequent reloads use its cookie.
  const [snapshot, setSnapshot] = useState(() => ({
    language: initialLanguage, dictionary: initialDictionary,
  }));
  const requestRef = useRef(0);
  const mountedRef = useRef(false);
  const currentRef = useRef(snapshot);
  currentRef.current = snapshot;

  const setLanguage = useCallback((language: LanguageCode) => {
    if (!isLanguageCode(language)) return;
    const request = ++requestRef.current;
    if (language === currentRef.current.language) {
      persistLanguage(language);
      return;
    }
    void loadDictionary(language).then((dictionary) => {
      if (!mountedRef.current || request !== requestRef.current) return;
      setSnapshot({ language, dictionary });
      persistLanguage(language);
    }).catch((error: unknown) => {
      if (mountedRef.current && request === requestRef.current) {
        console.warn("Language dictionary could not be loaded", error);
      }
    });
  }, [loadDictionary]);

  useEffect(() => {
    mountedRef.current = true;
    document.documentElement.dataset.hydrated = "true";
    setLanguage(preferredLanguage());
    const onStorage = (event: StorageEvent) => {
      if (event.key === LANGUAGE_STORAGE_KEY || event.key === null) {
        setLanguage(preferredLanguage());
      }
    };
    globalThis.window.addEventListener("storage", onStorage);
    return () => {
      mountedRef.current = false;
      ++requestRef.current;
      globalThis.window.removeEventListener("storage", onStorage);
    };
  }, [setLanguage]);

  useEffect(() => {
    // Register only the selected date locale; imported locale modules are cached.
    let active = true;
    void loadDateLocale(snapshot.language).then(() => {
      if (active) dayjs.locale(snapshot.language);
    }).catch(() => {});
    document.documentElement.lang = snapshot.language;
    return () => { active = false; };
  }, [snapshot.language]);

  const translate = useCallback((path: string, replacements?: Record<string, string | number>) =>
    applyReplacements(
      resolvePath(snapshot.dictionary, path) ?? resolvePath(pl, path) ?? path,
      replacements,
    ), [snapshot.dictionary]);

  const value = useMemo(() => ({
    language: snapshot.language, setLanguage, t: translate,
  }), [snapshot.language, setLanguage, translate]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() { return useContext(LanguageContext); }
export function useTranslation() { return useLanguage().t; }
