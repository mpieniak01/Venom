"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export type SelectMenuOption = {
  value: string;
  label?: string;
  description?: string;
  icon?: ReactNode;
  disabled?: boolean;
};

type SelectMenuProps = Readonly<{
  value: string;
  options: readonly SelectMenuOption[];
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
  const focusMenuOnOpen = useRef(false);
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
      if (event.key === "Escape") {
        if (menuRef.current?.contains(document.activeElement)) {
          triggerRef.current?.querySelector("button")?.focus();
        }
        setOpen(false);
      }
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
      const margin = 8;
      const menuHeight = Math.min(
        menuRef.current?.getBoundingClientRect().height ?? 0,
        Math.max(0, globalThis.window.innerHeight - margin * 2),
      );
      const below = rect.bottom + margin;
      const top = below + menuHeight <= globalThis.window.innerHeight - margin
        ? below
        : Math.max(margin, rect.top - margin - menuHeight);
      setMenuStyle(
        menuWidth === "content"
          ? {
            position: "fixed",
            top,
            left: rect.left,
            minWidth: rect.width,
            maxWidth: "90vw",
            width: "max-content",
            maxHeight: "calc(100vh - 16px)",
            overflowY: "auto",
            zIndex: 80,
          }
          : {
            position: "fixed",
            top,
            left: rect.left,
            width: rect.width,
            maxHeight: "calc(100vh - 16px)",
            overflowY: "auto",
            zIndex: 80,
          },
      );
    };
    updatePosition();
    if (focusMenuOnOpen.current) {
      const selected = menuRef.current?.querySelector<HTMLButtonElement>('button[aria-selected="true"]:not(:disabled)');
      (selected ?? menuRef.current?.querySelector<HTMLButtonElement>("button:not(:disabled)"))?.focus({ preventScroll: true });
      focusMenuOnOpen.current = false;
    }
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
        onClick={(event) => {
          focusMenuOnOpen.current = event.detail === 0;
          setOpen((prev) => !prev);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" && !open) {
            event.preventDefault();
            focusMenuOnOpen.current = true;
            setOpen(true);
          }
        }}
        className={cn(
          "flex min-w-0 items-center gap-2 rounded-full border border-[color:var(--ui-border)] bg-[color:var(--button-outline-bg)] px-3 py-1.5 text-xs uppercase tracking-wider text-[color:var(--button-outline-text)] transition hover:border-[color:var(--ui-border-strong)] hover:bg-[color:var(--button-outline-hover)] focus:outline-none disabled:cursor-not-allowed disabled:opacity-60",
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
            {currentOption?.label ?? currentOption?.value ?? placeholder}
          </span>
        )}
        <ChevronDown className="h-3 w-3 text-[color:var(--ui-muted)]" aria-hidden />
      </button>
      {open &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            ref={menuRef}
            role="listbox"
            tabIndex={-1}
            onKeyDown={(event) => {
              if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
              const choices = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
              if (!choices.length) return;
              event.preventDefault();
              const index = choices.indexOf(document.activeElement as HTMLButtonElement);
              let next = index;
              switch (event.key) {
                case "Home":
                  next = 0;
                  break;
                case "End":
                  next = choices.length - 1;
                  break;
                case "ArrowDown":
                  next = (index + 1) % choices.length;
                  break;
                case "ArrowUp":
                  next = index <= 0 ? choices.length - 1 : index - 1;
                  break;
              }
              choices[next].focus();
            }}
            style={menuStyle}
            className={cn(
              "rounded-2xl border border-[color:var(--ui-border)] bg-[color:var(--ui-menu-bg)] p-1 text-left text-[color:var(--text-primary)] shadow-xl",
              menuClassName,
            )}
            data-testid={menuTestId}
          >
            {uniqueOptions.length === 0 ? (
              <div className="px-3 py-2 text-xs text-[color:var(--ui-muted)]">Brak opcji</div>
            ) : (
              uniqueOptions.map((option) => {
                const active = option.value === value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    role="option"
                    aria-selected={active}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-[color:var(--text-primary)] transition hover:bg-[color:var(--ui-surface-hover)] disabled:cursor-not-allowed disabled:opacity-60",
                      active ? "bg-[color:var(--ui-menu-item-active)]" : "",
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
                      triggerRef.current?.querySelector("button")?.focus();
                    }}
                    disabled={option.disabled}
                  >
                    {renderOption ? (
                      renderOption(option, active)
                    ) : (
                      <>
                        {option.icon}
                        <div className="flex flex-col text-left">
                          <span className="text-xs uppercase tracking-[0.3em] text-[color:var(--ui-muted)]">
                            {option.label ?? option.value}
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
