"use client";

type BrainMetricCardProps = {
  label: string;
  value: string | number;
  hint: string;
};

export function BrainMetricCard({ label, value, hint }: BrainMetricCardProps) {
  return (
    <div className="card-shell card-base p-4 text-sm">
      <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">{label}</p>
      <p className="mt-2 text-3xl font-semibold">{value}</p>
      <p className="text-hint">{hint}</p>
    </div>
  );
}
