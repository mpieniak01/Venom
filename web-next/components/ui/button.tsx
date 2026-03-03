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
      "border border-[color:var(--btn-macro-border)] bg-[color:var(--btn-macro-bg)] text-[color:var(--btn-macro-text)] shadow-neon hover:border-[color:var(--btn-macro-hover-border)] hover:-translate-y-[1px]",
    secondary:
      "border border-[color:var(--button-secondary-border)] bg-[color:var(--button-secondary-bg)] text-[color:var(--button-secondary-text)] hover:bg-[color:var(--button-secondary-hover)]",
    outline:
      "border border-[color:var(--button-outline-border)] bg-[color:var(--button-outline-bg)] text-[color:var(--button-outline-text)] hover:bg-[color:var(--button-outline-hover)]",
    ghost:
      "border border-transparent bg-transparent text-[color:var(--button-ghost-text)] hover:bg-[color:var(--button-ghost-hover)]",
    subtle:
      "border border-[color:var(--button-subtle-border)] bg-[color:var(--button-subtle-bg)] text-[color:var(--button-subtle-text)] hover:border-[color:var(--button-subtle-hover-border)]",
    warning:
      "border border-[color:var(--btn-warning-border)] bg-[color:var(--btn-warning-bg)] text-[color:var(--btn-warning-text)] hover:border-[color:var(--btn-warning-hover-border)]",
    amber:
      "border border-[color:var(--btn-amber-border)] bg-[color:var(--btn-amber-bg)] text-[color:var(--btn-amber-text)] hover:border-[color:var(--btn-amber-hover-border)] hover:bg-[color:var(--btn-amber-hover-bg)]",
    danger:
      "border border-[color:var(--btn-danger-border)] bg-[color:var(--btn-danger-bg)] text-[color:var(--btn-danger-text)] hover:border-[color:var(--btn-danger-hover-border)]",
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
