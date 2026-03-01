import type { ReactNode } from "react";

type HeroStatProps = Readonly<{
  icon: ReactNode;
  label: string;
  primary: string;
  hint: string;
}>;

export function HeroStat({ icon, label, primary, hint }: HeroStatProps) {
  return (
    <div className="flex items-center gap-3 rounded-2xl box-base px-4 py-3">
      <span className="rounded-full border border-white/10 bg-black/40 p-2">
        {icon}
      </span>
      <div>
        <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
        <p className="text-xl font-semibold text-white">{primary}</p>
        <p className="text-hint">{hint}</p>
      </div>
    </div>
  );
}
