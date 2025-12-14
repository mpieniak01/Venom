import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type EmptyStateProps = {
  icon?: ReactNode;
  title: string;
  description?: string;
  className?: string;
};

export function EmptyState({ icon, title, description, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-start gap-1 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-zinc-400",
        className,
      )}
    >
      {icon && <div className="text-white">{icon}</div>}
      <p className="font-semibold text-white">{title}</p>
      {description && <p className="text-xs text-zinc-500">{description}</p>}
    </div>
  );
}
