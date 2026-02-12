"use client";

type TokenEfficiencyStatProps = Readonly<{
  label: string;
  value: string | number | null;
  hint: string;
}>;

export function TokenEfficiencyStat({ label, value, hint }: TokenEfficiencyStatProps) {
  return (
    <div className="rounded-2xl box-muted p-3">
      <p className="text-caption">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-white">{value ?? "—"}</p>
      <p className="text-hint">{hint}</p>
    </div>
  );
}

type TokenShareBarProps = Readonly<{
  label: string;
  percent: number | null;
  accent: string;
}>;

export function TokenShareBar({ label, percent, accent }: TokenShareBarProps) {
  return (
    <div className="rounded-2xl box-base p-3">
      <div className="flex items-center justify-between text-sm text-white">
        <span>{label}</span>
        <span>{percent !== null ? `${percent}%` : "—"}</span>
      </div>
      <div className="mt-2 h-2 rounded-full bg-white/5">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${accent}`}
          style={{ width: percent !== null ? `${Math.min(percent, 100)}%` : "0%" }}
        />
      </div>
    </div>
  );
}

type ResourceMetricCardProps = Readonly<{
  label: string;
  value: string;
  hint?: string;
}>;

export function ResourceMetricCard({ label, value, hint }: ResourceMetricCardProps) {
  return (
    <div className="rounded-2xl box-muted p-3 text-sm text-white">
      <p className="text-caption">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
      {hint ? <p className="text-hint">{hint}</p> : null}
    </div>
  );
}
