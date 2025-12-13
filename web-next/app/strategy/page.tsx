import { Badge } from "@/components/ui/badge";
import { Panel, StatCard } from "@/components/ui/panel";

const kpis = [
  { label: "Postęp ogólny", value: "48%", hint: "wg ukończonych milestones" },
  { label: "Milestones", value: "6 / 12", hint: "complete / total", accent: "blue" },
  { label: "Tasks", value: "42 / 87", hint: "complete / total", accent: "green" },
];

export default function StrategyPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl border border-[--color-border] bg-[--color-panel]/70 p-6 shadow-xl shadow-black/40">
        <p className="text-sm text-[--color-muted]">War Room</p>
        <h1 className="mt-2 text-3xl font-semibold">Strategia i roadmapa</h1>
        <p className="mt-2 text-sm text-[--color-muted]">
          Next.js widok dla War Room. Dane z /api/v1/strategy (wizja, milestones,
          roadmapa), akcje start/refresh/report.
        </p>
        <div className="mt-4 flex gap-2">
          <Badge tone="neutral">/strategy (custom API)</Badge>
          <Badge tone="warning">SSR/ISR możliwe</Badge>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {kpis.map((kpi) => (
          <StatCard
            key={kpi.label}
            label={kpi.label}
            value={kpi.value}
            hint={kpi.hint}
            accent={(kpi.accent as "purple" | "green" | "blue") || "purple"}
          />
        ))}
      </div>

      <Panel
        title="Wizja"
        description="Treść wizji pobrana z API (render Markdown + linki)."
      >
        <div className="rounded-xl border border-[--color-border] bg-white/5 p-4 text-sm text-[--color-muted]">
          Placeholder: Wizja produktu / misja. Do podmiany na dane z /strategy.
        </div>
      </Panel>

      <Panel title="Milestones" description="Lista kamieni milowych + tasks.">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-xl border border-[--color-border] bg-white/5 p-4">
            <p className="text-sm font-semibold text-white">MVP Next Cockpit</p>
            <p className="text-xs text-[--color-muted]">
              UI parity dla Cockpit + Flow + Brain.
            </p>
          </div>
          <div className="rounded-xl border border-[--color-border] bg-white/5 p-4">
            <p className="text-sm font-semibold text-white">E2E smoke</p>
            <p className="text-xs text-[--color-muted]">
              Playwright pokrywa task submit, telemetry, history.
            </p>
          </div>
        </div>
      </Panel>
    </div>
  );
}
