"use client";

import { useMemo } from "react";
import { Globe } from "lucide-react";
import { useLanguage, useTranslation, type LanguageCode } from "@/lib/i18n";
import { SelectMenu, type SelectMenuOption } from "@/components/ui/select-menu";

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
  const options = useMemo<SelectMenuOption[]>(
    () =>
      LANGUAGE_OPTIONS.map((option) => ({
        value: option.code,
        label: option.label,
        description: option.name,
        icon: <FlagIcon code={option.code} />,
      })),
    [],
  );
  const currentLanguage = useMemo(
    () => options.find((option) => option.value === language) ?? options[0],
    [language, options],
  );

  return (
    <SelectMenu
      value={language}
      options={options}
      onChange={(value) => setLanguage(value as LanguageCode)}
      ariaLabel={t("common.switchLanguage")}
      className={className}
      renderButton={() => (
        <>
          <Globe className="h-4 w-4 text-emerald-200" aria-hidden />
          {currentLanguage?.icon}
          <span>{currentLanguage?.label}</span>
        </>
      )}
      renderOption={(option) => (
        <>
          {option.icon}
          <div className="flex flex-col text-left">
            <span className="text-xs uppercase tracking-[0.3em] text-zinc-400">
              {option.label}
            </span>
            <span className="text-sm">{option.description}</span>
          </div>
        </>
      )}
    />
  );
}
