"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Globe } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLanguage, useTranslation, type LanguageCode } from "@/lib/i18n";

const LANGUAGE_OPTIONS = [
  { code: "pl", flag: "🇵🇱", label: "PL", name: "Polski" },
  { code: "en", flag: "🇬🇧", label: "EN", name: "English" },
  { code: "de", flag: "🇩🇪", label: "DE", name: "Deutsch" },
] as const;

function FlagIcon({ code }: { code: LanguageCode }) {
  if (code === "pl") {
    return (
      <svg viewBox="0 0 24 16" className="h-4 w-6 rounded-sm shadow-sm">
        <rect width="24" height="16" fill="#f4f4f5" />
        <rect y="8" width="24" height="8" fill="#d32f45" />
      </svg>
    );
  }
  if (code === "en") {
    return (
      <svg viewBox="0 0 24 16" className="h-4 w-6 rounded-sm shadow-sm">
        <rect width="24" height="16" fill="#1f2a44" />
        <path
          d="M0 1.5L22.5 16H24v-1.5L1.5 0H0v1.5zM24 1.5L1.5 16H0v-1.5L22.5 0H24v1.5z"
          fill="#f4f4f5"
        />
        <path
          d="M10 0h4v16h-4V0zM0 6h24v4H0V6z"
          fill="#f04b59"
        />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 16" className="h-4 w-6 rounded-sm shadow-sm">
      <rect width="24" height="16" fill="#000" />
      <rect y="5.33" width="24" height="5.34" fill="#dd0000" />
      <rect y="10.67" width="24" height="5.33" fill="#ffce00" />
    </svg>
  );
}

export function LanguageSwitcher({ className }: { className?: string }) {
  const { language, setLanguage } = useLanguage();
  const t = useTranslation();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLDivElement | null>(null);
  const currentLanguage = useMemo(
    () => LANGUAGE_OPTIONS.find((option) => option.code === language) ?? LANGUAGE_OPTIONS[0],
    [language],
  );

  useEffect(() => {
    const handleOutside = (event: MouseEvent) => {
      if (!triggerRef.current) return;
      if (!triggerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("mousedown", handleOutside);
    window.addEventListener("keydown", handleEsc);
    return () => {
      window.removeEventListener("mousedown", handleOutside);
      window.removeEventListener("keydown", handleEsc);
    };
  }, []);

  return (
    <div className={cn("relative z-40", className)} ref={triggerRef}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-xs uppercase tracking-wider text-white transition hover:border-white/40 hover:bg-white/5 focus:outline-none"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t("common.switchLanguage")}
      >
        <Globe className="h-4 w-4 text-emerald-200" aria-hidden />
        <FlagIcon code={language} />
        <span>{currentLanguage.label}</span>
        <ChevronDown className="h-3 w-3 text-zinc-400" aria-hidden />
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-44 rounded-2xl border border-white/10 bg-zinc-950/95 p-1 text-left shadow-xl">
          {LANGUAGE_OPTIONS.map((option) => (
            <button
              key={option.code}
              type="button"
              className={cn(
                "flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-white transition hover:bg-emerald-500/10",
                option.code === language ? "bg-white/10" : "",
              )}
              onClick={() => {
                setLanguage(option.code);
                setOpen(false);
              }}
            >
              <FlagIcon code={option.code} />
              <div className="flex flex-col text-left">
                <span className="text-xs uppercase tracking-[0.3em] text-zinc-400">{option.label}</span>
                <span className="text-sm">{option.name}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
