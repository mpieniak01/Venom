import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: "success" | "warning" | "danger" | "neutral";
  children: ReactNode;
};

export function Badge({ tone = "neutral", children, className, ...rest }: BadgeProps) {
  const styles = {
    success: "bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)] border-[color:var(--badge-success-border)]",
    warning: "bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)] border-[color:var(--badge-warning-border)]",
    danger: "bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)] border-[color:var(--badge-danger-border)]",
    neutral: "bg-[color:var(--badge-neutral-bg)] text-[color:var(--badge-neutral-text)] border-[color:var(--badge-neutral-border)]",
  }[tone];

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
