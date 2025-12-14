import type { ReactNode } from "react";

type PanelProps = {
  eyebrow?: string;
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
};

export function Panel({ eyebrow, title, description, action, children }: PanelProps) {
  return (
    <section className="glass-panel w-full rounded-panel shadow-card px-6 py-5">
      {(title || description || action) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div>
            {eyebrow && (
              <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">{eyebrow}</p>
            )}
            {title && (
              <h3 className="text-lg font-semibold leading-tight">{title}</h3>
            )}
            {description && (
              <p className="mt-1 text-sm text-[--color-muted]">{description}</p>
            )}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

type StatCardProps = {
  label: string;
  value: string | number;
  hint?: string;
  accent?: "purple" | "green" | "blue";
};

export function StatCard({ label, value, hint, accent = "purple" }: StatCardProps) {
  const accentColor =
    accent === "green"
      ? "from-emerald-500/20 to-emerald-500/5 border-emerald-500/30"
      : accent === "blue"
        ? "from-sky-500/20 to-sky-500/5 border-sky-500/30"
        : "from-purple-500/25 to-purple-500/5 border-purple-500/30";

  return (
    <div
      className={`rounded-xl border bg-gradient-to-br ${accentColor} px-4 py-3 shadow-inner shadow-black/20`}
    >
      <p className="text-xs uppercase tracking-wide text-[--color-muted]">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
      {hint && <p className="mt-1 text-xs text-zinc-400">{hint}</p>}
    </div>
  );
}
