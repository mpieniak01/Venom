"use client";

import type { ReactNode } from "react";

type OverlayFallbackProps = {
  icon: ReactNode;
  title: string;
  description: string;
  hint?: string;
  testId?: string;
};

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
      className="flex items-start gap-4 rounded-3xl border border-white/10 bg-gradient-to-r from-white/10 via-transparent to-white/5 p-4 text-sm text-white"
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-black/40 text-xl text-emerald-200">
        {icon}
      </div>
      <div>
        <p className="text-base font-semibold text-white">{title}</p>
        <p className="text-xs text-zinc-400">{description}</p>
        {hint && <p className="mt-2 text-[11px] uppercase tracking-[0.3em] text-zinc-500">{hint}</p>}
      </div>
    </div>
  );
}
