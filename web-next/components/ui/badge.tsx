import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: "success" | "warning" | "danger" | "neutral";
  variant?: "default" | "secondary" | "outline" | "destructive";
  children: ReactNode;
};

const VARIANT_TO_TONE: Record<NonNullable<BadgeProps["variant"]>, NonNullable<BadgeProps["tone"]>> = {
  default: "success",
  secondary: "neutral",
  outline: "warning",
  destructive: "danger",
};

export function Badge({ tone = "neutral", variant, children, className, ...rest }: BadgeProps) {
  const effectiveTone = variant ? VARIANT_TO_TONE[variant] : tone;
  const styles = {
    success: "bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)] border-[color:var(--badge-success-border)]",
    warning: "bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)] border-[color:var(--badge-warning-border)]",
    danger: "bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)] border-[color:var(--badge-danger-border)]",
    neutral: "bg-[color:var(--badge-neutral-bg)] text-[color:var(--badge-neutral-text)] border-[color:var(--badge-neutral-border)]",
  }[effectiveTone];

  return (
    <span
      {...rest}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium",
        styles,
        className,
      )}
    >
      {children}
    </span>
  );
}
