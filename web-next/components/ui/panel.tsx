import type { ReactNode } from "react";

type PanelProps = Readonly<{
  eyebrow?: string;
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}>;

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

type StatCardProps = Readonly<{
  label: string;
  value: string | number;
  hint?: string;
  accent?: StatCardAccent;
  suppressHydrationWarning?: boolean;
}>;

export function StatCard({ label, value, hint, accent = "purple", suppressHydrationWarning }: StatCardProps) {
  const accentPalette: Record<StatCardAccent, string> = {
    purple: "from-violet-500/16 via-violet-500/8 to-transparent border-violet-400/35",
    green: "from-emerald-500/14 via-emerald-500/8 to-transparent border-emerald-400/35",
    blue: "from-sky-500/14 via-sky-500/8 to-transparent border-sky-400/35",
    violet: "from-fuchsia-500/14 via-fuchsia-500/8 to-transparent border-fuchsia-400/35",
    indigo: "from-indigo-500/14 via-indigo-500/8 to-transparent border-indigo-400/35",
  };

  const accentColor = accentPalette[accent] ?? accentPalette.purple;

  return (
    <div
      className={`rounded-xl border bg-[color:var(--surface-overlay-soft)] bg-gradient-to-br ${accentColor} px-4 py-3 shadow-[inset_0_1px_0_var(--ui-border)] backdrop-blur-md`}
    >
      <p className="text-xs uppercase tracking-wide text-theme-muted">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold text-theme-primary" suppressHydrationWarning={suppressHydrationWarning}>
        {value}
      </p>
      {hint && <p className="mt-1 text-hint">{hint}</p>}
    </div>
  );
}
