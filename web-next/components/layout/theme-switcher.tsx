"use client";

import { useMemo, useSyncExternalStore } from "react";
import { Palette } from "lucide-react";
import { SelectMenu, type SelectMenuOption } from "@/components/ui/select-menu";
import { useTheme } from "@/lib/theme";
import { useTranslation } from "@/lib/i18n";
import { DEFAULT_THEME, THEME_REGISTRY, isThemeId } from "@/lib/theme-registry";

export function ThemeSwitcher({ className }: Readonly<{ className?: string }>) {
  const { theme, setTheme, availableThemes } = useTheme();
  const t = useTranslation();
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  const options = useMemo<SelectMenuOption[]>(
    () =>
      availableThemes.map((themeId) => {
        const keyBase = THEME_REGISTRY[themeId].translationKey;
        return {
          value: themeId,
          label: t(`${keyBase}.short`),
          description: t(`${keyBase}.description`),
        };
      }),
    [availableThemes, t],
  );

  const current = useMemo(() => {
    const target = mounted ? theme : DEFAULT_THEME;
    return options.find((option) => option.value === target) ?? options[0];
  }, [mounted, options, theme]);

  return (
    <SelectMenu
      value={theme}
      options={options}
      onChange={(next) => {
        if (isThemeId(next)) {
          setTheme(next);
        }
      }}
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
