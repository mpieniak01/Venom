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
      className="card-shell bg-gradient-to-r from-white/10 via-transparent to-white/5 flex items-start gap-4 p-4 text-sm"
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl box-muted text-xl text-emerald-200">
        {icon}
      </div>
      <div>
        <p className="text-base font-semibold text-white">{title}</p>
        <p className="text-xs text-muted">{description}</p>
        {hint && <p className="mt-2 text-caption">{hint}</p>}
      </div>
    </div>
  );
}
