"use client";

import { forwardRef, type ButtonHTMLAttributes } from "react";
import { Slot } from "@radix-ui/react-slot";
import { cn } from "@/lib/utils";

export type ButtonVariant =
  | "primary"
  | "macro"
  | "secondary"
  | "outline"
  | "ghost"
  | "subtle"
  | "warning"
  | "amber"
  | "danger";
export type ButtonSize = "xs" | "sm" | "md";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: boolean;
  asChild?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    className,
    variant = "primary",
    size = "md",
    icon = false,
    type = "button",
    asChild = false,
    children,
    ...props
  },
  ref,
) {
  const variantClass = {
    primary:
      "bg-gradient-to-r from-violet-600 to-indigo-500 text-white border border-white/10 shadow-neon hover:-translate-y-[1px]",
    macro:
      "border border-violet-300/50 bg-violet-500/30 text-white shadow-neon hover:border-violet-200/80 hover:-translate-y-[1px]",
    secondary:
      "border border-[color:var(--button-secondary-border)] bg-[color:var(--button-secondary-bg)] text-[color:var(--button-secondary-text)] hover:bg-[color:var(--button-secondary-hover)]",
    outline:
      "border border-[color:var(--button-outline-border)] bg-[color:var(--button-outline-bg)] text-[color:var(--button-outline-text)] hover:bg-[color:var(--button-outline-hover)]",
    ghost:
      "border border-transparent bg-transparent text-[color:var(--button-ghost-text)] hover:bg-[color:var(--button-ghost-hover)]",
    subtle:
      "border border-[color:var(--button-subtle-border)] bg-[color:var(--button-subtle-bg)] text-[color:var(--button-subtle-text)] hover:border-[color:var(--button-subtle-hover-border)]",
    warning:
      "border border-amber-500/40 bg-amber-500/10 text-amber-100 hover:border-amber-500/60",
    amber:
      "border-amber-500/30 bg-amber-500/10 text-amber-200 hover:border-amber-500/50 hover:bg-amber-500/20",
    danger:
      "border border-rose-500/40 bg-rose-500/10 text-rose-100 hover:border-rose-500/60",
  }[variant];

  const sizeClassBySize: Record<ButtonSize, string> = {
    xs: "px-2.5 py-1 text-[11px]",
    sm: "px-3.5 py-2 text-xs",
    md: "px-4 py-2.5 text-sm",
  };
  const sizeClass = sizeClassBySize[size];

  const Comp = asChild ? Slot : "button";

  return (
    <Comp
      ref={ref}
      type={asChild ? undefined : type}
      className={cn(
        "inline-flex items-center gap-2 rounded-full font-medium transition cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed",
        icon ? "justify-center" : "",
        variantClass,
        sizeClass,
        className,
      )}
      {...props}
    >
      {children}
    </Comp>
  );
});
