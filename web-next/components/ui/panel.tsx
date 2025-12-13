import type { ReactNode } from "react";

type PanelProps = {
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
};

export function Panel({ title, description, action, children }: PanelProps) {
  return (
    <section className="rounded-2xl border border-[--color-border] bg-[--color-panel]/80 p-6 shadow-lg shadow-black/30">
      {(title || description || action) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div>
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
      ? "from-emerald-500/30 to-emerald-500/5 border-emerald-500/30"
      : accent === "blue"
        ? "from-sky-500/30 to-sky-500/5 border-sky-500/30"
        : "from-purple-500/30 to-purple-500/5 border-purple-500/30";

  return (
    <div
      className={`rounded-xl border bg-gradient-to-br ${accentColor} px-4 py-3 shadow-inner shadow-black/20`}
    >
      <p className="text-xs uppercase tracking-wide text-[--color-muted]">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
      {hint && <p className="mt-1 text-xs text-[--color-muted]">{hint}</p>}
    </div>
  );
}
