"use client";

import { forwardRef, type ButtonHTMLAttributes } from "react";
import { Slot } from "@radix-ui/react-slot";
import { cn } from "@/lib/utils";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "outline"
  | "ghost"
  | "subtle"
  | "warning"
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
    secondary: "bg-white/5 text-white border border-white/10 hover:bg-white/10",
    outline: "border border-white/10 text-white hover:bg-white/5",
    ghost: "text-white hover:bg-white/5",
    subtle: "border border-white/5 bg-white/5 text-white hover:border-violet-500/40",
    warning:
      "border border-amber-500/40 bg-amber-500/10 text-amber-100 hover:border-amber-500/60",
    danger:
      "border border-rose-500/40 bg-rose-500/10 text-rose-100 hover:border-rose-500/60",
  }[variant];

  const sizeClass =
    size === "xs"
      ? "px-2.5 py-1 text-[11px]"
      : size === "sm"
        ? "px-3.5 py-2 text-xs"
        : "px-4 py-2.5 text-sm";

  const Comp = asChild ? Slot : "button";

  return (
    <Comp
      ref={ref}
      type={asChild ? undefined : type}
      className={cn(
        "inline-flex items-center gap-2 rounded-full font-medium transition disabled:opacity-60 disabled:cursor-not-allowed",
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
