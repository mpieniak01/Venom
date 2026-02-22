"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export type SelectMenuOption = {
  value: string;
  label: string;
  description?: string;
  icon?: ReactNode;
  disabled?: boolean;
};

type SelectMenuProps = Readonly<{
  value: string;
  options: SelectMenuOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  buttonTestId?: string;
  menuTestId?: string;
  optionTestIdPrefix?: string;
  className?: string;
  buttonClassName?: string;
  menuClassName?: string;
  optionClassName?: string;
  disabled?: boolean;
  menuWidth?: "trigger" | "content";
  renderButton?: (option: SelectMenuOption | null) => ReactNode;
  renderOption?: (option: SelectMenuOption, active: boolean) => ReactNode;
}>;

export function SelectMenu({
  value,
  options,
  onChange,
  placeholder = "Wybierz",
  ariaLabel,
  buttonTestId,
  menuTestId,
  optionTestIdPrefix,
  className,
  buttonClassName,
  menuClassName,
  optionClassName,
  disabled,
  menuWidth = "trigger",
  renderButton,
  renderOption,
}: SelectMenuProps) {
  const uniqueOptions = useMemo(() => {
    const seen = new Set<string>();
    return options.filter((option) => {
      const key = (option.value || "").trim();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [options]);

  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLDivElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [menuStyle, setMenuStyle] = useState<React.CSSProperties>({});
  const currentOption = useMemo(
    () => options.find((option) => option.value === value) ?? null,
    [options, value],
  );

  useEffect(() => {
    const handleOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!triggerRef.current) return;
      if (triggerRef.current.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    globalThis.window.addEventListener("mousedown", handleOutside);
    globalThis.window.addEventListener("keydown", handleEsc);
    return () => {
      globalThis.window.removeEventListener("mousedown", handleOutside);
      globalThis.window.removeEventListener("keydown", handleEsc);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const updatePosition = () => {
      if (!triggerRef.current) return;
      const rect = triggerRef.current.getBoundingClientRect();
      setMenuStyle(
        menuWidth === "content"
          ? {
            position: "fixed",
            top: rect.bottom + 8,
            left: rect.left,
            minWidth: rect.width,
            maxWidth: "90vw",
            width: "max-content",
            zIndex: 80,
          }
          : {
            position: "fixed",
            top: rect.bottom + 8,
            left: rect.left,
            width: rect.width,
            zIndex: 80,
          },
      );
    };
    updatePosition();
    globalThis.window.addEventListener("resize", updatePosition);
    globalThis.window.addEventListener("scroll", updatePosition, true);
    return () => {
      globalThis.window.removeEventListener("resize", updatePosition);
      globalThis.window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, menuWidth]);

  return (
    <div className={cn("relative", className)} ref={triggerRef}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          "flex min-w-0 items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-xs uppercase tracking-wider text-white transition hover:border-white/40 hover:bg-white/5 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60",
          buttonClassName,
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        data-testid={buttonTestId}
        disabled={disabled}
        suppressHydrationWarning
      >
        {renderButton ? (
          renderButton(currentOption)
        ) : (
          <span className="min-w-0 flex-1 truncate text-left">
            {currentOption?.label ?? placeholder}
          </span>
        )}
        <ChevronDown className="h-3 w-3 text-zinc-400" aria-hidden />
      </button>
      {open &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            ref={menuRef}
            style={menuStyle}
            className={cn(
              "mt-2 rounded-2xl border border-white/10 bg-zinc-950/95 p-1 text-left shadow-xl",
              menuClassName,
            )}
            data-testid={menuTestId}
          >
            {uniqueOptions.length === 0 ? (
              <div className="px-3 py-2 text-xs text-zinc-500">Brak opcji</div>
            ) : (
              uniqueOptions.map((option) => {
                const active = option.value === value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    className={cn(
                      "flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-white transition hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-60",
                      active ? "bg-white/10" : "",
                      optionClassName,
                    )}
                    data-testid={
                      optionTestIdPrefix ? `${optionTestIdPrefix}-${option.value}` : undefined
                    }
                    data-value={option.value}
                    onClick={() => {
                      if (option.disabled) return;
                      onChange(option.value);
                      setOpen(false);
                    }}
                    disabled={option.disabled}
                  >
                    {renderOption ? (
                      renderOption(option, active)
                    ) : (
                      <>
                        {option.icon}
                        <div className="flex flex-col text-left">
                          <span className="text-xs uppercase tracking-[0.3em] text-zinc-400">
                            {option.label}
                          </span>
                          {option.description && (
                            <span className="text-sm">{option.description}</span>
                          )}
                        </div>
                      </>
                    )}
                  </button>
                );
              })
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}
