"use client";

type LessonStatEntry = { label: string; value: string | number; hint?: string };

type LessonStatsProps = {
  entries: LessonStatEntry[];
};

export function LessonStats({ entries }: LessonStatsProps) {
  if (!entries.length) {
    return (
      <p className="rounded-2xl border border-dashed border-white/10 bg-black/20 px-3 py-2 text-hint">
        Brak statystyk Lessons.
      </p>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {entries.map((entry) => (
        <div
          key={entry.label}
          className="rounded-2xl box-base p-3 text-sm text-white"
        >
          <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">{entry.label}</p>
          <p className="mt-1 text-2xl font-semibold">{entry.value}</p>
          {entry.hint && <p className="text-hint">{entry.hint}</p>}
        </div>
      ))}
    </div>
  );
}
