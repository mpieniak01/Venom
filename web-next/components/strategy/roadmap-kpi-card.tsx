"use client";

const SOURCE_LABEL = "Źródło:";

type RoadmapKpiCardProps = {
  label: string;
  value: string;
  description: string;
  percent: number;
  tone?: "violet" | "indigo" | "emerald";
  source?: string;
};

const toneGradients: Record<NonNullable<RoadmapKpiCardProps["tone"]>, string> = {
  violet: "from-violet-500/70 via-violet-500/30 to-violet-500/10",
  indigo: "from-indigo-500/70 via-indigo-500/30 to-indigo-500/10",
  emerald: "from-emerald-500/70 via-emerald-500/30 to-emerald-500/10",
};

export function RoadmapKpiCard({
  label,
  value,
  description,
  percent,
  tone = "violet",
  source,
}: RoadmapKpiCardProps) {
  const safePercent = Math.min(Math.max(percent, 0), 100);

  return (
    <div className="card-shell card-base p-4 text-sm">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">{label}</p>
        {source && <p className="text-xs text-zinc-600">{SOURCE_LABEL} {source}</p>}
      </div>
      <div className="mt-2 flex items-center justify-between">
        <p className="text-2xl font-semibold">{value}</p>
        <p className="text-hint">{description}</p>
      </div>
      <div className="mt-4 h-2 rounded-full bg-black/30">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${toneGradients[tone]}`}
          style={{ width: `${safePercent}%` }}
        />
      </div>
      <p className="mt-2 text-hint">{safePercent.toFixed(1)}% completion</p>
    </div>
  );
}
