import type { ReactNode } from "react";

type PanelProps = {
  eyebrow?: string;
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function Panel({ eyebrow, title, description, action, children, className }: PanelProps) {
  return (
    <section className={`glass-panel w-full rounded-panel shadow-card px-6 py-5 ${className ?? ""}`}>
      {(title || description || action) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div>
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            {title && (
              <h3 className="heading-h3 leading-tight">{title}</h3>
            )}
            {description && <p className="mt-1 text-sm text-muted">{description}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

type StatCardAccent = "purple" | "green" | "blue" | "violet" | "indigo";

type StatCardProps = {
  label: string;
  value: string | number;
  hint?: string;
  accent?: StatCardAccent;
};

export function StatCard({ label, value, hint, accent = "purple" }: StatCardProps) {
  const accentPalette: Record<StatCardAccent, string> = {
    purple: "from-purple-500/25 to-purple-500/5 border-purple-500/30",
    green: "from-emerald-500/20 to-emerald-500/5 border-emerald-500/30",
    blue: "from-sky-500/20 to-sky-500/5 border-sky-500/30",
    violet: "from-violet-500/20 to-violet-500/5 border-violet-500/30",
    indigo: "from-indigo-500/20 to-indigo-500/5 border-indigo-500/30",
  };

  const accentColor = accentPalette[accent] ?? accentPalette.purple;

  return (
    <div
      className={`rounded-xl border bg-gradient-to-br ${accentColor} px-4 py-3 shadow-inner shadow-black/20`}
    >
      <p className="text-xs uppercase tracking-wide text-[--color-muted]">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
      {hint && <p className="mt-1 text-hint">{hint}</p>}
    </div>
  );
}
