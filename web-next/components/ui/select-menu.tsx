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

type SelectMenuProps = {
  value: string;
  options: SelectMenuOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
  buttonClassName?: string;
  menuClassName?: string;
  optionClassName?: string;
  disabled?: boolean;
  renderButton?: (option: SelectMenuOption | null) => ReactNode;
  renderOption?: (option: SelectMenuOption, active: boolean) => ReactNode;
};

export function SelectMenu({
  value,
  options,
  onChange,
  placeholder = "Wybierz",
  ariaLabel,
  className,
  buttonClassName,
  menuClassName,
  optionClassName,
  disabled,
  renderButton,
  renderOption,
}: SelectMenuProps) {
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
      if (menuRef.current && menuRef.current.contains(target)) return;
      {
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

  useEffect(() => {
    if (!open) return;
    const updatePosition = () => {
      if (!triggerRef.current) return;
      const rect = triggerRef.current.getBoundingClientRect();
      setMenuStyle({
        position: "fixed",
        top: rect.bottom + 8,
        left: rect.left,
        width: rect.width,
        zIndex: 80,
      });
    };
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  return (
    <div className={cn("relative", className)} ref={triggerRef}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          "flex items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-xs uppercase tracking-wider text-white transition hover:border-white/40 hover:bg-white/5 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60",
          buttonClassName,
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        disabled={disabled}
      >
        {renderButton ? (
          renderButton(currentOption)
        ) : (
          <span className="flex-1 text-left">
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
          >
            {options.length === 0 ? (
              <div className="px-3 py-2 text-xs text-zinc-500">Brak opcji</div>
            ) : (
              options.map((option) => {
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
