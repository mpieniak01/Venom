"use client";

import type { ReactNode } from "react";

type OverlayFallbackProps = Readonly<{
  icon: ReactNode;
  title: string;
  description: string;
  hint?: string;
  testId?: string;
}>;

export function OverlayFallback({
  icon,
  title,
  description,
  hint,
  testId,
}: OverlayFallbackProps) {
  return (
    <div
      data-testid={testId}
      className="card-shell bg-gradient-to-r from-[color:var(--ui-surface-hover)] via-transparent to-[color:var(--ui-surface-hover)] flex items-start gap-4 p-4 text-sm"
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl box-muted text-xl text-[color:var(--primary)]">
        {icon}
      </div>
      <div>
        <p className="text-base font-semibold text-[color:var(--text-primary)]">{title}</p>
        <p className="text-xs text-muted">{description}</p>
        {hint && <p className="mt-2 text-caption">{hint}</p>}
      </div>
    </div>
  );
}
