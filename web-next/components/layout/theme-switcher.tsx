"use client";

import { useMemo, useSyncExternalStore } from "react";
import { Palette } from "lucide-react";
import { SelectMenu, type SelectMenuOption } from "@/components/ui/select-menu";
import { useTheme, type ThemeId } from "@/lib/theme";
import { useTranslation } from "@/lib/i18n";

export function ThemeSwitcher({ className }: Readonly<{ className?: string }>) {
  const { theme, setTheme } = useTheme();
  const t = useTranslation();
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  const options = useMemo<SelectMenuOption[]>(
    () => [
      {
        value: "venom-dark",
        label: t("theme.options.venomDark.short"),
        description: t("theme.options.venomDark.description"),
      },
      {
        value: "venom-light-dev",
        label: t("theme.options.venomLightDev.short"),
        description: t("theme.options.venomLightDev.description"),
      },
    ],
    [t],
  );

  const current = useMemo(() => {
    const target = mounted ? theme : "venom-dark";
    return options.find((option) => option.value === target) ?? options[0];
  }, [mounted, options, theme]);

  return (
    <SelectMenu
      value={theme}
      options={options}
      onChange={(next) => setTheme(next as ThemeId)}
      ariaLabel={t("common.switchTheme")}
      className={className}
      buttonTestId="topbar-theme-switcher"
      optionTestIdPrefix="theme-option"
      menuWidth="content"
      renderButton={() => (
        <>
          <Palette className="h-4 w-4 text-[color:var(--accent)]" aria-hidden />
          <span className="hidden md:inline-flex">{t("theme.label")}</span>
          <span>{current?.label}</span>
        </>
      )}
      renderOption={(option) => (
        <div className="flex flex-col text-left">
          <span className="text-xs uppercase tracking-[0.3em] text-[color:var(--ui-muted)]">
            {option.label}
          </span>
          <span className="text-sm">{option.description}</span>
        </div>
      )}
    />
  );
}
