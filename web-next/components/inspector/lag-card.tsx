"use client";

type LatencyCardProps = {
  label: string;
  value: string;
  hint: string;
};

export function LatencyCard({ label, value, hint }: LatencyCardProps) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-4 text-sm text-white shadow-card">
      <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">{label}</p>
      <p className="mt-2 text-3xl font-semibold">{value}</p>
      <p className="text-xs text-zinc-400">{hint}</p>
    </div>
  );
}
