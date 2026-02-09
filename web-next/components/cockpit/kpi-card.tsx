"use client";

import type { ReactNode } from "react";

type CockpitMetricCardProps = Readonly<{
  primaryValue: string;
  secondaryLabel?: string;
  progress?: number | null;
  footer?: string;
}>;

export function CockpitMetricCard({ primaryValue, secondaryLabel, progress, footer }: CockpitMetricCardProps) {
  return (
    <div className="card-shell card-base p-5 text-sm">
      <div className="flex items-center justify-between">
        <p className="text-4xl font-semibold">{primaryValue}</p>
        {secondaryLabel && <p className="text-xs text-zinc-400">{secondaryLabel}</p>}
      </div>
      {typeof progress === "number" && (
        <div className="mt-4 h-2 rounded-full bg-black/30">
          <div
            className="h-full rounded-full bg-gradient-to-r from-emerald-400 via-emerald-500 to-emerald-600"
            style={{ width: `${Math.min(Math.max(progress, 0), 100)}%` }}
          />
        </div>
      )}
      {footer && <p className="mt-2 text-xs text-zinc-400">{footer}</p>}
    </div>
  );
}

type TokenSplit = {
  label: string;
  value: number;
};

type CockpitTokenCardProps = Readonly<{
  totalValue?: number;
  splits: TokenSplit[];
  chartSlot?: ReactNode;
}>;

export function CockpitTokenCard({ totalValue, splits, chartSlot }: CockpitTokenCardProps) {
  return (
    <div className="card-shell card-base p-5 text-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Zużycie tokenów</p>
          <p className="text-4xl font-semibold">
            {typeof totalValue === "number" ? totalValue.toLocaleString("pl-PL") : "—"}
          </p>
        </div>
      </div>
      <div className="mt-4 space-y-2">
        {splits.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-white/10 bg-black/20 px-3 py-2 text-xs text-zinc-500">
            Brak danych o tokenach.
          </p>
        ) : (
          splits.map((split) => (
            <div key={split.label} className="flex items-center justify-between rounded-2xl box-subtle px-3 py-2">
              <span className="text-xs uppercase tracking-[0.35em] text-zinc-500">{split.label}</span>
              <span className="text-base font-semibold text-white">{split.value.toLocaleString("pl-PL")}</span>
            </div>
          ))
        )}
      </div>
      {chartSlot && <div className="mt-4" data-testid="token-history-chart">{chartSlot}</div>}
    </div>
  );
}
