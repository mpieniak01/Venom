import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

type ListCardProps = {
  title: ReactNode;
  subtitle?: ReactNode;
  badge?: ReactNode;
  meta?: ReactNode;
  icon?: ReactNode;
  selected?: boolean;
  onClick?: () => void;
  children?: ReactNode;
};

export function ListCard({
  title,
  subtitle,
  badge,
  meta,
  icon,
  selected,
  onClick,
  children,
}: ListCardProps) {
  const Component = onClick ? "button" : "div";

  return (
    <Component
      className={cn(
        "w-full rounded-2xl border px-3 py-3 text-left transition",
        onClick ? "cursor-pointer hover:bg-white/10" : "cursor-default",
        selected ? "border-violet-500/40 bg-violet-500/10" : "border-white/5 bg-white/5",
      )}
      onClick={onClick}
      type={onClick ? "button" : undefined}
    >
      <div className="flex items-start justify-between gap-2">
        {icon && <div className="text-white">{icon}</div>}
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-white">{title}</p>
          {subtitle && <p className="mt-1 text-xs text-muted">{subtitle}</p>}
        </div>
        {badge}
      </div>
      {meta && <div className="mt-2 text-[11px] text-muted">{meta}</div>}
      {children}
    </Component>
  );
}
