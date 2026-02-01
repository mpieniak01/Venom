"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { pl } from "./locales/pl";
import { en } from "./locales/en";
import { de } from "./locales/de";
import dayjs from "dayjs";
import "dayjs/locale/pl";
import "dayjs/locale/en";
import "dayjs/locale/de";
import relativeTime from "dayjs/plugin/relativeTime";

dayjs.extend(relativeTime);

const STORAGE_KEY = "venom-language";

const translations = {
  pl,
  en,
  de,
};

export type LanguageCode = keyof typeof translations;

type LanguageContextValue = {
  language: LanguageCode;
  setLanguage: (code: LanguageCode) => void;
  t: (path: string, replacements?: Record<string, string | number>) => string;
};

const LanguageContext = createContext<LanguageContextValue>({
  language: "pl",
  setLanguage: () => { },
  t: (path: string) => path,
});

function resolvePath(locale: Record<string, unknown>, path: string): string | null {
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
  return Object.entries(replacements).reduce((acc, [key, replacement]) => {
    const pattern = new RegExp(`{{\\s*${key}\\s*}}`, "g");
    return acc.replace(pattern, String(replacement));
  }, value);
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<LanguageCode>("pl");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(STORAGE_KEY) as LanguageCode | null;
    if (stored && stored in translations) {
      setLanguage(stored);
      return;
    }
    const browser = window.navigator.language?.slice(0, 2).toLowerCase();
    if (browser && (browser === "en" || browser === "de")) {
      setLanguage(browser as LanguageCode);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(STORAGE_KEY, language);
    dayjs.locale(language);
  }, [language]);

  const translate = useCallback(
    (path: string, replacements?: Record<string, string | number>) => {
      const value =
        resolvePath(translations[language], path) ??
        resolvePath(translations.pl, path) ??
        path;
      return applyReplacements(value, replacements);
    },
    [language],
  );

  const value = useMemo(
    () => ({
      language,
      setLanguage,
      t: translate,
    }),
    [language, translate],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  return useContext(LanguageContext);
}

export function useTranslation() {
  const { t } = useLanguage();
  return t;
}
