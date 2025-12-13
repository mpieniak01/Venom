import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";

const graphMeta = [
  { label: "Węzły", value: "356" },
  { label: "Krawędzie", value: "1 204" },
  { label: "Ostatnia aktualizacja", value: "8 min temu" },
];

export default function BrainPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl border border-[--color-border] bg-[--color-panel]/70 p-6 shadow-xl shadow-black/40">
        <p className="text-sm text-[--color-muted]">Brain / Knowledge Graph</p>
        <h1 className="mt-2 text-3xl font-semibold">Wizualizacja pamięci</h1>
        <p className="mt-2 text-sm text-[--color-muted]">
          Widok grafu zasila /api/v1/graph/summary i /api/v1/graph/scan. Rendering
          planowany z użyciem Cytoscape (dynamic import).
        </p>
        <div className="mt-4 flex gap-2">
          <Badge tone="neutral">/graph/summary</Badge>
          <Badge tone="neutral">/graph/scan</Badge>
          <Badge tone="warning">Cytoscape (client)</Badge>
        </div>
      </div>

      <Panel title="Statystyki grafu" description="Stub danych do zastąpienia API.">
        <div className="grid gap-3 sm:grid-cols-3">
          {graphMeta.map((item) => (
            <div
              key={item.label}
              className="rounded-xl border border-[--color-border] bg-white/5 p-4"
            >
              <p className="text-xs uppercase tracking-wide text-[--color-muted]">
                {item.label}
              </p>
              <p className="mt-2 text-xl font-semibold">{item.value}</p>
            </div>
          ))}
        </div>
      </Panel>

      <Panel
        title="Obszary filtrów"
        description="Tagi, typy węzłów, ostatnie aktualizacje — do wpięcia w API grafu."
      >
        <div className="flex flex-wrap gap-2 text-sm text-[--color-muted]">
          <Badge tone="neutral">kod</Badge>
          <Badge tone="neutral">workflow</Badge>
          <Badge tone="neutral">dokumentacja</Badge>
          <Badge tone="neutral">lekcje</Badge>
        </div>
      </Panel>

      <Panel
        title="Widok grafu"
        description="Miejsce na komponent grafu (Cytoscape) + szczegóły węzła."
      >
        <div className="grid gap-4 md:grid-cols-3">
          <div className="md:col-span-2 rounded-xl border border-dashed border-[--color-border] bg-white/5 p-6 text-sm text-[--color-muted]">
            Placeholder grafu. Po stronie klienta wpiąć Cytoscape + style z planu.
          </div>
          <div className="rounded-xl border border-[--color-border] bg-white/5 p-6">
            <h4 className="text-sm font-semibold text-white">Szczegóły węzła</h4>
            <p className="mt-2 text-sm text-[--color-muted]">
              Tu pojawi się panel szczegółów (tagi, relacje, ostatnie akcji agentów).
            </p>
          </div>
        </div>
      </Panel>
    </div>
  );
}
