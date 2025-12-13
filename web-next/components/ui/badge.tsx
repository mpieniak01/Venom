import type { ReactNode } from "react";

type BadgeProps = {
  tone?: "success" | "warning" | "danger" | "neutral";
  children: ReactNode;
};

export function Badge({ tone = "neutral", children }: BadgeProps) {
  const styles = {
    success: "bg-emerald-500/15 text-emerald-200 border-emerald-400/30",
    warning: "bg-amber-500/15 text-amber-200 border-amber-400/30",
    danger: "bg-rose-500/15 text-rose-200 border-rose-400/30",
    neutral: "bg-white/5 text-slate-200 border-white/10",
  }[tone];

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium ${styles}`}
    >
      {children}
    </span>
  );
}
